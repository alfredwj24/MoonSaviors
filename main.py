"""
main.py — Moon Saviors
======================
Entry point for the Moon Saviors 2-player co-op vertical platformer.

Run with:
    python main.py

Architecture overview (university report)
-----------------------------------------
The Game class owns a single pygame display surface and a finite-state
machine (FSM) that determines which screen / level is active.  Each state
has exactly one active object (a UI screen or a Level) that implements the
three-method contract:

    handle_event(event)   — process one pygame.Event
    update()              — advance simulation / animation by one frame
    draw(surface)         — render current frame onto *surface*

Transitions between states are triggered by reading a `next_state` attribute
(for UI screens) or by inspecting the event queue returned by level.get_events().
The FSM never has ambiguous in-between states: the old object is discarded and
the new one is constructed before the next frame begins, so there is never a
frame where two states are simultaneously active.

Screen-shake is applied in draw(): the entire game surface is blitted to the
display with a random offset supplied by ScreenEffect.offset, then the
surrounding border is filled black.  This keeps shake logic entirely out of
all game-object draw methods.
"""

import sys
import pygame

# ---------------------------------------------------------------------------
# Config — all constants and paths imported before anything else
# ---------------------------------------------------------------------------
from config import (
    # Display
    SCREEN_WIDTH, SCREEN_HEIGHT, FPS, SCREEN_TITLE,
    # Game states
    STATE_MENU, STATE_CHARACTER_SELECT,
    STATE_LEVEL1, STATE_LEVEL2,
    STATE_GAME_OVER, STATE_WIN,
    # Audio volumes
    MUSIC_VOLUME, SFX_VOLUME,
    # Music paths (for transition management)
    MUSIC_CHARACTER_SELECT, MUSIC_LEVEL1, MUSIC_LEVEL2,
    # Colours
    BLACK, WHITE,
    # Player defaults
    PLAYER_LIVES,
    # Character IDs
    CHAR_LUNA, CHAR_NOVA, CHAR_ORION,
)

# ---------------------------------------------------------------------------
# Game modules — imported after config so they can safely reference it
# ---------------------------------------------------------------------------
from effects import ScreenEffect, ParticleSystem
from player  import create_player, CONTROLS_P1, CONTROLS_P2
from level   import Level1, Level2
from ui      import (
    MainMenu,
    CharacterSelectScreen,
    HUD,
    GameOverScreen,
    WinScreen,
)


# ---------------------------------------------------------------------------
# AUDIO MANAGER
# ---------------------------------------------------------------------------

class AudioManager:
    """
    Centralised controller for music and SFX volume.

    University report:
      Pygame's mixer distinguishes between *music* (streamed, one track at a
      time via pygame.mixer.music) and *sounds* (buffered pygame.mixer.Sound
      objects).  AudioManager wraps the music side, providing a clean
      transition method so callers never need to call pygame.mixer.music
      directly.  SFX volume is applied at load time inside each module that
      creates Sound objects; AudioManager exposes set_sfx_volume() so the
      main menu could offer a volume slider in future without touching every
      Sound call site.
    """

    def __init__(self):
        self._current_music_path: str | None = None
        self.music_volume: float = MUSIC_VOLUME
        self.sfx_volume:   float = SFX_VOLUME
        pygame.mixer.music.set_volume(self.music_volume)

    def play_music(self, path: str, loops: int = -1) -> None:
        """
        Load and stream *path* if it is not already playing.

        The guard on self._current_music_path prevents the common mistake of
        restarting the same track every frame when update() is called
        repeatedly in the same state.

        Parameters
        ----------
        path  : Absolute path to the music file (from config.py).
        loops : Number of loops; -1 = infinite (default).
        """
        if self._current_music_path == path:
            return   # already playing this track — do nothing
        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(self.music_volume)
            pygame.mixer.music.play(loops)
            self._current_music_path = path
        except (FileNotFoundError, pygame.error):
            # Missing music file: log and continue silently
            print(f"[AudioManager] Warning: could not load music '{path}'")
            self._current_music_path = None

    def stop_music(self) -> None:
        """Fade out the current track over 0.5 s and clear the cached path."""
        pygame.mixer.music.fadeout(500)
        self._current_music_path = None

    def set_music_volume(self, vol: float) -> None:
        """Set music volume in range [0.0, 1.0]."""
        self.music_volume = max(0.0, min(1.0, vol))
        pygame.mixer.music.set_volume(self.music_volume)

    def set_sfx_volume(self, vol: float) -> None:
        """
        Store the target SFX volume.

        Note: existing Sound objects already loaded keep their own volume
        setting; this only affects sounds created after this call via any
        module that reads AudioManager.sfx_volume.
        """
        self.sfx_volume = max(0.0, min(1.0, vol))


# ---------------------------------------------------------------------------
# GAME
# ---------------------------------------------------------------------------

class Game:
    """
    Top-level game controller.

    Owns
    ----
    • The pygame display surface.
    • A permanent off-screen buffer (*_world_surf*) that the active state
      draws onto each frame.  The buffer is then blitted to the display with
      the ScreenEffect shake offset applied.  This design means ScreenEffect
      only needs to modify one blit call rather than every individual draw.
    • The FSM: one active state object at a time.
    • ScreenEffect (shared across all states so shake/flash carry across
      state transitions if needed).
    • AudioManager for music transitions.
    • HUD (created once and reused between Level1 and Level2).

    State machine diagram
    ---------------------
        MENU
          │  Start pressed
          ▼
    CHARACTER_SELECT
          │  Both players confirmed
          ▼
        LEVEL1
          │  Crystal collected         │  Both players dead
          ▼                            ▼
         WIN ──────────────────── GAME_OVER
          │  Continue / Level 2        │  Retry
          ▼                            ▼
        LEVEL2                       LEVEL1
          │  Both players dead
          ▼
       GAME_OVER
          │  Main Menu
          ▼
         MENU
    """

    def __init__(self):
        # ----------------------------------------------------------------
        # Pygame initialisation
        # ----------------------------------------------------------------
        # Configure the mixer BEFORE pygame.init().  pre_init() only affects the
        # NEXT mixer initialisation, and pygame.init() already starts the mixer
        # with default settings — so calling pre_init() afterwards (as before)
        # was a no-op and the low-latency 512-sample buffer never took effect.
        # frequency=44100, size=-16 (signed 16-bit), channels=2 (stereo),
        # buffer=512 (low latency for SFX)
        pygame.mixer.pre_init(44100, -16, 2, 512)
        pygame.init()
        pygame.mixer.init()

        # ---- Display ----
        self._display = pygame.display.set_mode(
            (SCREEN_WIDTH, SCREEN_HEIGHT), pygame.DOUBLEBUF
        )
        pygame.display.set_caption(SCREEN_TITLE)

        # Set window icon if the asset exists (graceful skip if missing)
        try:
            from config import FX_MOON_CRYSTAL
            icon = pygame.image.load(FX_MOON_CRYSTAL).convert_alpha()
            icon = pygame.transform.smoothscale(icon, (32, 32))
            pygame.display.set_icon(icon)
        except Exception:
            pass

        # ---- Off-screen world buffer ----
        # All game rendering happens here; the buffer is then blitted to the
        # display with a shake offset.  This is the key technique that makes
        # ScreenEffect.shake() work without modifying any draw call.
        self._world_surf = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))

        # ---- Clock ----
        self._clock = pygame.time.Clock()

        # ---- Shared services ----
        self.screen_effect  = ScreenEffect()   # shake, flash, freeze-tint
        self.audio          = AudioManager()

        # ---- State machine ----
        self._state: str         = STATE_MENU
        self._active_object      = None   # current screen or level
        self._transitioning: bool = False  # guard against double transitions

        # ---- Player configuration (set during CHARACTER_SELECT) ----
        # Stored here so Level1 and Level2 can reuse the same character
        # choices without going back to the select screen.
        self._p1_char: str | None = None
        self._p2_char: str | None = None
        self._pending_level: str = STATE_LEVEL1
        self._last_level_state: str = STATE_LEVEL1

        # ---- Player instances (created when entering a level) ----
        # Kept as instance variables so the HUD and win/game-over screens
        # can read final stats (lives, crystals) after the level ends.
        self._player1 = None
        self._player2 = None

        # ---- HUD (reused across both levels) ----
        # Created here so it loads its icon assets once.
        self._hud: HUD | None = None

        # ---- Score tracking (persists from Level2 across state changes) ----
        self._final_score:      int = 0
        self._final_high_score: int = 0

        # ---- Start in MENU state ----
        self._enter_state(STATE_MENU)

    # ------------------------------------------------------------------
    # Main game loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        """
        Main loop — runs at FPS until the window is closed or the game quits.

        University report — game loop structure:
          Each iteration of the loop follows the canonical
          Input → Update → Render order.

          1. handle_events() — read the pygame event queue and route each
             event to the active state object.
          2. update()        — advance the active state by one frame.
          3. draw()          — render the active state, apply post-processing
             (shake offset), and flip the display buffer.
          4. clock.tick(FPS) — sleep for the remainder of the frame to maintain
             a consistent 60 FPS regardless of rendering speed.

          The loop exits when self._state is set to "QUIT" by handle_events().
        """
        while self._state != "QUIT":
            dt = self._clock.tick(FPS)   # milliseconds since last frame (unused
                                          # here but useful for future dt-based
                                          # physics)

            self.handle_events()
            self.update()
            self.draw()

        # ---- Clean shutdown ----
        pygame.mixer.music.stop()
        pygame.quit()
        sys.exit(0)

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    def handle_events(self) -> None:
        """
        Drain the pygame event queue and route each event.

        Global events (quit, volume keys) are handled here before forwarding
        to the active state object.  This keeps the state objects from needing
        to duplicate quit logic.

        University report:
          Separating global events from state-specific events is a common
          pattern in game FSMs.  It means adding a global pause key or
          screenshot shortcut only requires a change here, not in every state.
        """
        for event in pygame.event.get():

            # ---- Quit ----
            if event.type == pygame.QUIT:
                self._state = "QUIT"
                return

            # ---- Global keyboard shortcuts ----
            if event.type == pygame.KEYDOWN:
                # ESC from any non-menu state → return to menu
                if event.key == pygame.K_ESCAPE:
                    if self._state not in (STATE_MENU, STATE_CHARACTER_SELECT):
                        self._enter_state(STATE_MENU)
                        return

                # M — mute / unmute music
                if event.key == pygame.K_m:
                    current = pygame.mixer.music.get_volume()
                    pygame.mixer.music.set_volume(0.0 if current > 0 else
                                                  self.audio.music_volume)

            # ---- Forward to active state ----
            if self._active_object and hasattr(self._active_object, "handle_event"):
                self._active_object.handle_event(event)

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(self) -> None:
        """
        Advance the current state by one frame.

        Each state branch:
          1. Calls the active object's update() method (or passes player/key
             context for levels).
          2. Checks for a state-transition signal.
          3. Calls _enter_state() if a transition is needed.

        University report:
          The ScreenEffect is updated every frame regardless of state so that
          shake and flash timers tick down correctly even when overlaid on
          menu screens (e.g. the flash triggered at the end of Level 1 should
          continue into the WIN screen).
        """
        self.screen_effect.update()

        if self._active_object is None:
            return

        # ----------------------------------------------------------------
        # MENU
        # ----------------------------------------------------------------
        if self._state == STATE_MENU:
            self._active_object.update()
            next_s = getattr(self._active_object, "next_state", None)
            if next_s in (STATE_LEVEL1, STATE_LEVEL2):
                # Go to character select before starting the chosen level
                self._pending_level = next_s
                self._enter_state(STATE_CHARACTER_SELECT)
            elif next_s == "QUIT":
                self._state = "QUIT"

        # ----------------------------------------------------------------
        # CHARACTER SELECT
        # ----------------------------------------------------------------
        elif self._state == STATE_CHARACTER_SELECT:
            self._active_object.update()
            next_s = getattr(self._active_object, "next_state", None)
            if next_s in (STATE_LEVEL1, STATE_LEVEL2):
                # Store character choices for both players
                self._p1_char = self._active_object.p1_character
                self._p2_char = self._active_object.p2_character
                self._enter_state(next_s)

        # ----------------------------------------------------------------
        # LEVEL 1 — Rescue Mission
        # ----------------------------------------------------------------
        elif self._state == STATE_LEVEL1:
            keys = pygame.key.get_pressed()
            self._player1.update(self._active_object.platforms, keys)
            self._player2.update(self._active_object.platforms, keys)
            self._active_object.update(
                [self._player1, self._player2], keys
            )

            # Read level event queue for game-logic transitions
            for evt in self._active_object.get_events():
                if evt == "WIN":
                    self._enter_state(STATE_WIN)
                    return
                if evt == "MOONQUAKE":
                    pass   # already handled inside Level1.update()

            # If both players are dead, game over
            if not self._player1.alive and not self._player2.alive:
                self._enter_state(STATE_GAME_OVER)

        # ----------------------------------------------------------------
        # LEVEL 2 — Endless Ascent
        # ----------------------------------------------------------------
        elif self._state == STATE_LEVEL2:
            keys = pygame.key.get_pressed()
            self._player1.update(self._active_object.platforms, keys)
            self._player2.update(self._active_object.platforms, keys)
            self._active_object.update(
                [self._player1, self._player2], keys
            )

            for evt in self._active_object.get_events():
                if evt == "GAME_OVER":
                    self._final_score      = self._active_object.score
                    self._final_high_score = self._active_object.high_score
                    self._enter_state(STATE_GAME_OVER)
                    return

        # ----------------------------------------------------------------
        # WIN SCREEN
        # ----------------------------------------------------------------
        elif self._state == STATE_WIN:
            self._active_object.update()
            next_s = getattr(self._active_object, "next_state", None)
            if next_s == STATE_MENU:
                self._enter_state(STATE_MENU)

        # ----------------------------------------------------------------
        # GAME OVER SCREEN
        # ----------------------------------------------------------------
        elif self._state == STATE_GAME_OVER:
            self._active_object.update()
            next_s = getattr(self._active_object, "next_state", None)
            if next_s in (STATE_LEVEL1, STATE_LEVEL2):
                # Retry: recreate players with fresh lives, same characters
                self._enter_state(next_s)
            elif next_s == STATE_MENU:
                self._enter_state(STATE_MENU)

    # ------------------------------------------------------------------
    # Draw
    # ------------------------------------------------------------------

    def draw(self) -> None:
        """
        Render the active state onto the world buffer, then blit to display.

        Screen-shake implementation (university report):
          Rather than offsetting every individual sprite draw call, the entire
          game world is rendered to self._world_surf (a Surface the same size
          as the window).  The world surface is then blitted to the display at
          position (shake_dx, shake_dy) supplied by ScreenEffect.offset.
          The display is first filled with BLACK so the shake gap around the
          edges is a solid black border rather than leftover pixels.

        Draw order per state:
          1. Active state draws itself onto self._world_surf.
          2. Players draw themselves on top (during level states).
          3. HUD draws on top of players (during level states).
          4. ScreenEffect flash draws last (covers everything).
          5. World surface is blitted to display with shake offset.
          6. pygame.display.flip() swaps the back buffer.
        """
        # ---- Clear world buffer ----
        self._world_surf.fill(BLACK)

        # ---- Render active state ----
        if self._active_object is None:
            pygame.display.flip()
            return

        # --- Menu screens — draw directly; no players / HUD ---
        if self._state in (STATE_MENU,
                           STATE_CHARACTER_SELECT,
                           STATE_WIN,
                           STATE_GAME_OVER):
            self._active_object.draw(self._world_surf)

        # --- Level states — draw level, then players, then HUD ---
        elif self._state in (STATE_LEVEL1, STATE_LEVEL2):
            self._active_object.draw(self._world_surf)

            # Draw players on top of the level background / platforms.
            # scroll_y converts world coordinates to screen coordinates:
            #   screen_y = world_y - scroll_y
            # Player.draw() accepts scroll_y and subtracts it internally so
            # the sprite renders at the correct visible position on screen.
            scroll_y = getattr(self._active_object, "scroll_y", 0)
            if self._player1:
                self._player1.draw(self._world_surf, scroll_y)
            if self._player2:
                self._player2.draw(self._world_surf, scroll_y)

            # Draw the HUD above everything except the flash overlay
            if self._hud:
                score      = getattr(self._active_object, "score",      0)
                high_score = getattr(self._active_object, "high_score", 0)
                self._hud.draw(
                    self._world_surf,
                    self._player1,
                    self._player2,
                    level_type = self._state,
                    score      = score,
                    high_score = high_score,
                )

            # Screen flash is drawn inside level.draw() via screen_effect,
            # so it appears above the HUD.  We do NOT draw it again here to
            # avoid double-flashing.

        # ----------------------------------------------------------------
        # Apply shake offset and blit world to display
        # ----------------------------------------------------------------
        shake_dx, shake_dy = self.screen_effect.offset
        self._display.fill(BLACK)   # clear any shake-border remnants
        self._display.blit(self._world_surf, (shake_dx, shake_dy))

        # ---- Flip (swap back-buffer to screen) ----
        pygame.display.flip()

    # ------------------------------------------------------------------
    # State machine
    # ------------------------------------------------------------------

    def _enter_state(self, new_state: str) -> None:
        """
        Transition the FSM to *new_state*.

        Steps
        -----
        1. Tear down the old state object (sets _active_object to None first
           so any draw call during teardown sees no active object).
        2. Construct the new state object.
        3. Start appropriate background music.
        4. Store the new object in _active_object and update _state.

        University report:
          Constructing a fresh object for each state entry means all timers,
          cursors, and animation counters start from zero.  There is no risk
          of stale state leaking between plays.  The only persistent data
          across states are the player character choices (_p1_char, _p2_char)
          and the final score, which are stored as Game attributes and passed
          explicitly into the new state's constructor.
        """
        # Prevent re-entrant transitions (e.g. two events firing in the same
        # frame both trying to enter a new state)
        if self._transitioning:
            return
        self._transitioning = True

        # ---- Discard old object ----
        self._active_object = None

        # ---- Build new object and start music ----

        if new_state == STATE_MENU:
            self._active_object = MainMenu()
            # MainMenu streams the level 1 background track for atmosphere
            self.audio.play_music(MUSIC_LEVEL1, loops=-1)

        elif new_state == STATE_CHARACTER_SELECT:
            self._active_object = CharacterSelectScreen(self._pending_level)
            self.audio.play_music(MUSIC_CHARACTER_SELECT, loops=-1)

        elif new_state == STATE_LEVEL1:
            self._last_level_state = STATE_LEVEL1
            self._final_score = 0
            self._final_high_score = 0
            # ---- Create fresh player instances ----
            # If character choices are set (from CharacterSelectScreen), use
            # them; otherwise fall back to sensible defaults so the game can
            # still be tested without going through character select.
            p1_char = self._p1_char or CHAR_LUNA
            p2_char = self._p2_char or CHAR_ORION

            self._player1 = create_player(
                p1_char,
                x             = SCREEN_WIDTH  // 4,
                y             = SCREEN_HEIGHT - 200,
                controls      = CONTROLS_P1,
                screen_effect = self.screen_effect,
            )
            self._player2 = create_player(
                p2_char,
                x             = 3 * SCREEN_WIDTH // 4,
                y             = SCREEN_HEIGHT - 200,
                controls      = CONTROLS_P2,
                screen_effect = self.screen_effect,
            )

            # Inject the particle system so players can emit landing dust
            self._player1.particle_system = None  # will be set after level build
            self._player2.particle_system = None

            # ---- Build level ----
            self._active_object = Level1(self.screen_effect)

            # Share the level's particle system with the players
            self._player1.particle_system = self._active_object.particles
            self._player2.particle_system = self._active_object.particles

            # ---- Reposition players directly ON the starting platform ----
            # Platform world_y = WORLD_HEIGHT - 80 = 3920.
            # Placing players at (platform_y - sprite_height) means they
            # land immediately on frame 1 with no gap to fall across.
            start_y = self._active_object._start_platform_y - self._player1.SPRITE_HEIGHT
            self._player1.reset_position(SCREEN_WIDTH // 4,     start_y)
            self._player2.reset_position(3 * SCREEN_WIDTH // 4, start_y)

            # ---- HUD ----
            self._hud = HUD(
                p1_name = p1_char.upper(),
                p2_name = p2_char.upper(),
            )

            self.audio.play_music(MUSIC_LEVEL1, loops=-1)

        elif new_state == STATE_LEVEL2:
            self._last_level_state = STATE_LEVEL2
            self._final_score = 0
            self._final_high_score = 0
            p1_char = self._p1_char or CHAR_LUNA
            p2_char = self._p2_char or CHAR_NOVA
            self._player1 = create_player(
                p1_char,
                x=SCREEN_WIDTH // 4, y=SCREEN_HEIGHT - 200,
                controls=CONTROLS_P1, screen_effect=self.screen_effect,
            )
            self._player2 = create_player(
                p2_char,
                x=3 * SCREEN_WIDTH // 4, y=SCREEN_HEIGHT - 200,
                controls=CONTROLS_P2, screen_effect=self.screen_effect,
            )

            # ---- Build level ----
            self._active_object = Level2(self.screen_effect)

            # Share particle system with players
            self._player1.particle_system = self._active_object.particles
            self._player2.particle_system = self._active_object.particles

            # Position players on the starting platform
            # Place players directly on the starting platform (world coords)
            lv2_start_y = self._active_object._start_platform_y - self._player1.SPRITE_HEIGHT
            self._player1.reset_position(SCREEN_WIDTH // 4,     lv2_start_y)
            self._player2.reset_position(3 * SCREEN_WIDTH // 4, lv2_start_y)

            # ---- HUD ----
            self._hud = HUD(
                p1_name = p1_char.upper(),
                p2_name = p2_char.upper(),
            )

            self.audio.play_music(MUSIC_LEVEL2, loops=-1)

        elif new_state == STATE_WIN:
            p1_crystals = getattr(self._player1, "crystals", 0)
            p2_crystals = getattr(self._player2, "crystals", 0)
            self._active_object = WinScreen(
                p1_crystals=p1_crystals,
                p2_crystals=p2_crystals,
            )
            # WinScreen plays the victory sound internally; stop music so it
            # doesn't clash with the fanfare.
            self.audio.stop_music()

        elif new_state == STATE_GAME_OVER:
            self._active_object = GameOverScreen(
                score      = self._final_score,
                high_score = self._final_high_score,
                retry_state = self._last_level_state,
            )
            self.audio.stop_music()

        # ---- Finalise transition ----
        self._state         = new_state
        self._transitioning = False

    # ------------------------------------------------------------------
    # Developer utilities
    # ------------------------------------------------------------------

    def _debug_info(self) -> None:
        """
        Print one line of debug info to stdout each frame.

        Enable by calling self._debug_info() inside run().
        Kept out of the release loop to avoid the print overhead at 60 FPS.
        """
        fps  = self._clock.get_fps()
        p1ly = getattr(self._player1, "lives", "-")
        p2ly = getattr(self._player2, "lives", "-")
        print(
            f"[{self._state:<18}] "
            f"FPS={fps:5.1f}  "
            f"P1.lives={p1ly}  P2.lives={p2ly}  "
            f"shake={self.screen_effect.offset}",
            end="\r",
        )


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    """
    Programme entry point.

    University report:
      The `if __name__ == "__main__"` guard ensures that creating a Game
      instance (and therefore initialising pygame) only happens when the file
      is run directly.  If another module were to import main.py for testing
      purposes, the guard prevents the game window from opening automatically.
    """
    game = Game()
    game.run()
