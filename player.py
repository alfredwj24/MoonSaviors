"""
player.py — Moon Saviors
========================
Defines the base Player class and the three playable character subclasses:
  • Luna  — balanced; double jump, speed boost, shield bubble
  • Orion — high jumper; super jump, magnet pull, platform freeze
  • Nova  — speedster; fast movement, spark trail that reveals hidden platforms

Design pattern used (university report):
  Inheritance + composition.  Common physics, collision, rendering, and
  sound logic live in Player.  Each subclass only overrides or extends what
  is unique to that character.  Special-effect objects (ShieldBubble,
  SparkTrail) are *composed* into the relevant subclass rather than
  inherited, keeping the effect logic in effects.py and the character logic
  here.
"""

import pygame
import os
import math

from config import (
    # Physics
    GRAVITY, MAX_FALL_SPEED,
    PLAYER_WALK_SPEED, PLAYER_JUMP_FORCE,
    # Luna
    LUNA_SPEED_BOOST, LUNA_DOUBLE_JUMP_FORCE,
    COOLDOWN_LUNA_SHIELD,
    # Orion
    ORION_SUPER_JUMP_FORCE, ORION_MAGNET_RADIUS,
    ORION_FREEZE_DURATION, COOLDOWN_ORION_FREEZE,
    # Nova
    NOVA_DASH_SPEED, NOVA_DASH_DURATION,
    NOVA_SPARK_DURATION, COOLDOWN_NOVA_DASH,
    # Lives
    PLAYER_LIVES,
    # Sprite paths
    SPRITE_LUNA, SPRITE_NOVA, SPRITE_ORION,
    # Controls
    P1_LEFT, P1_RIGHT, P1_JUMP, P1_DOWN, P1_SPECIAL,
    P2_LEFT, P2_RIGHT, P2_JUMP, P2_DOWN, P2_SPECIAL,
    # Colours (fallback sprite tints)
    CYAN, PINK, GOLD, WHITE, BLACK,
    # Sound paths + global SFX volume
    SFX_JUMP, SFX_PLAYER_FALL, SFX_CRYSTAL_PICKUP, SFX_VOLUME,
    # Screen dimensions
    SCREEN_WIDTH, SCREEN_HEIGHT,
    # Character IDs
    CHAR_LUNA, CHAR_NOVA, CHAR_ORION,
)
from effects import ShieldBubble, SparkTrail


# ---------------------------------------------------------------------------
# CONTROL BINDING PRESETS
# Each preset is a dict mapping logical action → pygame key constant.
# Player.__init__ accepts any such dict, keeping the class input-agnostic.
# ---------------------------------------------------------------------------

CONTROLS_P1 = {
    "left"   : P1_LEFT,
    "right"  : P1_RIGHT,
    "jump"   : P1_JUMP,
    "down"   : P1_DOWN,
    "special": P1_SPECIAL,
}

CONTROLS_P2 = {
    "left"   : P2_LEFT,
    "right"  : P2_RIGHT,
    "jump"   : P2_JUMP,
    "down"   : P2_DOWN,
    "special": P2_SPECIAL,
}


# ---------------------------------------------------------------------------
# SOUND LOADER HELPER
# ---------------------------------------------------------------------------

def _load_sound(path: str) -> pygame.mixer.Sound | None:
    """
    Attempt to load a sound file from *path*.

    Returns None (silently) if the file is missing or the mixer is
    unavailable, so the game never crashes on a missing audio asset.
    """
    try:
        snd = pygame.mixer.Sound(path)
        snd.set_volume(SFX_VOLUME)
        return snd
    except (FileNotFoundError, pygame.error):
        return None


def _play(sound: pygame.mixer.Sound | None) -> None:
    """Play *sound* if it was successfully loaded."""
    if sound:
        sound.play()


# ---------------------------------------------------------------------------
# SPRITE LOADER HELPER
# ---------------------------------------------------------------------------

def _load_sprite(path: str, size: tuple[int, int],
                 fallback_color: tuple) -> pygame.Surface:
    """
    Load a sprite image from *path* and scale it to *size*.

    If the file is missing, a solid-coloured rectangle in *fallback_color*
    is returned so the game keeps running without the asset.

    University report note:
      Using convert_alpha() after loading preserves the PNG transparency
      channel and is faster to blit than a raw Surface because Pygame
      converts the pixel format to match the display surface once at load
      time rather than on every blit.
    """
    try:
        img = pygame.image.load(path).convert_alpha()
        return pygame.transform.smoothscale(img, size)
    except (FileNotFoundError, pygame.error):
        surf = pygame.Surface(size, pygame.SRCALPHA)
        surf.fill((*fallback_color, 220))
        return surf


# ---------------------------------------------------------------------------
# BASE PLAYER CLASS
# ---------------------------------------------------------------------------

class Player:
    """
    Base class for all playable characters.

    Responsibilities
    ----------------
    • Load and display the character sprite (with left/right flipping).
    • Store and update physics state: position, velocity, gravity, ground flag.
    • Handle platform collision detection and resolution.
    • Process key input via the injected *controls* dict.
    • Track lives, crystals, and damage/collection events.
    • Delegate screen-shake and sound playback to the ScreenEffect / mixer
      objects passed in at runtime (so Player has no hard dependency on the
      game loop).
    """

    # Visual size every sprite is scaled to (px)
    SPRITE_WIDTH  = 48
    SPRITE_HEIGHT = 72

    def __init__(
        self,
        x: float,
        y: float,
        sprite_path: str,
        controls: dict,
        fallback_color: tuple = (200, 200, 200),
        screen_effect=None,   # ScreenEffect instance injected by main.py
    ):
        # ---- Position & physics ----
        self.x: float = float(x)
        self.y: float = float(y)
        self.velocity_x: float = 0.0
        self.velocity_y: float = 0.0

        # ---- State flags ----
        self.on_ground: bool   = False
        self.facing_right: bool = True
        self.alive: bool       = True   # False when all lives are lost

        # ---- Game stats ----
        self.lives: int    = PLAYER_LIVES
        self.crystals: int = 0          # crystals collected (Level 2 scoring)

        # ---- Controls ----
        # A dict mapping action strings to pygame key constants, so the same
        # class works for both Player 1 (WASD) and Player 2 (arrow keys).
        self.controls = controls

        # ---- Visual ----
        self._sprite_orig = _load_sprite(
            sprite_path,
            (self.SPRITE_WIDTH, self.SPRITE_HEIGHT),
            fallback_color,
        )
        self._sprite = self._sprite_orig   # current frame (may be flipped)

        # ---- Collision rectangle ----
        # Rect is kept in sync with (self.x, self.y) every frame.
        self.rect = pygame.Rect(
            int(self.x),
            int(self.y),
            self.SPRITE_WIDTH,
            self.SPRITE_HEIGHT,
        )

        # ---- Sound effects ----
        self._snd_jump   = _load_sound(SFX_JUMP)
        self._snd_fall   = _load_sound(SFX_PLAYER_FALL)
        self._snd_crystal = _load_sound(SFX_CRYSTAL_PICKUP)

        # ---- External dependencies (injected, may be None) ----
        self.screen_effect = screen_effect   # ScreenEffect from effects.py
        self.particle_system = None          # ParticleSystem set by main.py

        # ---- Move speed (subclasses may override) ----
        self.move_speed: float = float(PLAYER_WALK_SPEED)

        # ---- Jump tracking ----
        self._jump_pressed_last: bool = False   # edge-detect for jump key
        self._jump_dust_pending: bool = False
        self._landing_dust_pending: bool = False

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def center(self) -> tuple[int, int]:
        """Return the centre pixel of the player's sprite."""
        return (
            int(self.x + self.SPRITE_WIDTH  // 2),
            int(self.y + self.SPRITE_HEIGHT // 2),
        )

    @property
    def feet(self) -> tuple[int, int]:
        """Return the bottom-centre pixel (useful for dust particles)."""
        return (
            int(self.x + self.SPRITE_WIDTH // 2),
            int(self.y + self.SPRITE_HEIGHT),
        )

    # ------------------------------------------------------------------
    # Core update loop
    # ------------------------------------------------------------------

    def update(self, platforms: list, keys: pygame.key.ScancodeWrapper) -> None:
        """
        Advance the player simulation by one frame.

        Order of operations (university report):
          1. Read keyboard input → apply horizontal velocity.
          2. Apply gravity → accumulate vertical velocity.
          3. Move player position by velocity.
          4. Resolve platform collisions (AABB, top-face only).
          5. Clamp position to screen boundaries.
          6. Synchronise self.rect with self.x / self.y.
          7. Update sprite orientation (flip if moving left).
          8. Call subclass hook _update_abilities() for cooldowns etc.

        Parameters
        ----------
        platforms : list of platform objects (must expose .rect attribute)
        keys      : result of pygame.key.get_pressed() passed in from main.py
        """
        # --- 1. Horizontal input ---
        moving = False
        if keys[self.controls["left"]]:
            self.velocity_x = -self.move_speed
            self.facing_right = False
            moving = True
        elif keys[self.controls["right"]]:
            self.velocity_x = self.move_speed
            self.facing_right = True
            moving = True
        else:
            # Friction: bleed off horizontal velocity when no key is held
            self.velocity_x *= 0.75

        # --- 2. Gravity ---
        # Capture on_ground BEFORE resetting it in step 3 so we can skip
        # gravity while the player is standing on a surface.  Applying
        # gravity every frame even when grounded causes a 1-pixel oscillation
        # each frame (the player falls 0.55 px, collides, snaps back — jitter).
        # Skipping gravity when grounded eliminates this completely.
        was_on_ground = self.on_ground
        if not was_on_ground:
            # Moon gravity is gentle (configured in config.py).
            # velocity_y is positive downward (Pygame's y-axis convention).
            self.velocity_y += GRAVITY
            if self.velocity_y > MAX_FALL_SPEED:
                self.velocity_y = MAX_FALL_SPEED

        # --- 3. Move ---
        # (was_on_ground already captured above)
        self.on_ground = False

        self.x += self.velocity_x
        self.y += self.velocity_y

        # --- 4. Platform collision ---
        self.rect.x = int(self.x)
        self.rect.y = int(self.y)
        self._resolve_platform_collisions(platforms, was_on_ground)

        # --- 5. Screen boundary clamp ---
        # Wrap horizontally (the player can re-enter from the opposite side).
        if self.x + self.SPRITE_WIDTH < 0:
            self.x = SCREEN_WIDTH
        elif self.x > SCREEN_WIDTH:
            self.x = -self.SPRITE_WIDTH

        # --- 6. Sync rect ---
        self.rect.x = int(self.x)
        self.rect.y = int(self.y)

        # --- 7. Sprite orientation ---
        if self.facing_right:
            self._sprite = self._sprite_orig
        else:
            # pygame.transform.flip returns a new surface; the original is
            # never mutated so flipping is cheap and correct every frame.
            self._sprite = pygame.transform.flip(self._sprite_orig, True, False)

        # --- 8. Subclass ability hook ---
        self._update_abilities(keys)

        # --- Jump (edge-detect so one key-press = one jump) ---
        jump_held = bool(keys[self.controls["jump"]])
        if jump_held and not self._jump_pressed_last:
            self.jump()
        self._jump_pressed_last = jump_held

        # --- Special ability (edge-detect) ---
        special_held = bool(keys[self.controls["special"]])
        if special_held and not getattr(self, "_special_pressed_last", False):
            self.use_special()
        self._special_pressed_last = special_held

    def _resolve_platform_collisions(
        self, platforms: list, was_on_ground: bool
    ) -> None:
        """
        AABB top-face collision: push the player above any platform they land on.

        University report — collision technique:
          We only resolve collisions on the TOP face of platforms (i.e. the
          player can jump through from below but lands when falling down onto
          the surface).  The condition `self.velocity_y >= 0` ensures we only
          snap upward when the player is moving downward or stationary — never
          when jumping upward through a platform.

          After resolving, we set self.on_ground = True and zero out
          velocity_y so gravity doesn't accumulate while standing.
        """
        for plat in platforms:
            # Skip hidden platforms that haven't been revealed yet
            if getattr(plat, "hidden", False) and not getattr(plat, "revealed", False):
                continue

            # Use a manual overlap test with >= so that "touching" (bottom
            # exactly equals platform top) counts as a collision.  pygame
            # colliderect uses strictly-greater-than, which misses this case
            # and causes a 1-frame jitter where the player drops 1 pixel then
            # snaps back every other frame.
            overlaps = (
                self.rect.bottom >= plat.rect.top and
                self.rect.top    <  plat.rect.bottom and
                self.rect.right  >  plat.rect.left and
                self.rect.left   <  plat.rect.right
            )

            if overlaps and self.velocity_y >= 0:
                # Only land if the player's feet were above the platform top
                # last frame — prevents sideways clipping registering as landing.
                feet_last_frame = self.y + self.SPRITE_HEIGHT - self.velocity_y
                if feet_last_frame <= plat.rect.top + 6:
                    self.y = plat.rect.top - self.SPRITE_HEIGHT
                    self.rect.y = int(self.y)
                    self.velocity_y = 0
                    self.on_ground  = True

                    # Landing dust is emitted during draw(), where scroll_y is
                    # available to convert the world-space feet position.
                    if not was_on_ground:
                        self._landing_dust_pending = True

                    # Notify crumbling platforms that weight is applied
                    if hasattr(plat, "on_player_land"):
                        plat.on_player_land()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def jump(self) -> None:
        """
        Perform a standard single jump if the player is on the ground.

        University report:
          PLAYER_JUMP_FORCE is negative (upward) in Pygame's coordinate
          system.  Assigning it directly to velocity_y gives an instant
          impulse; gravity then decelerates the player each frame until
          velocity_y becomes positive again and the arc begins to fall.
        """
        if self.on_ground:
            self.velocity_y = PLAYER_JUMP_FORCE
            self.on_ground  = False
            self._jump_dust_pending = True
            _play(self._snd_jump)

    def use_special(self) -> None:
        """
        Trigger the character's special ability.
        Overridden in each subclass; base version does nothing.
        """
        pass

    def _update_abilities(self, keys) -> None:
        """
        Per-frame ability timer updates.
        Overridden in each subclass; base version does nothing.
        """
        pass

    def take_damage(self) -> None:
        """
        Deduct one life and trigger fall feedback.

        University report:
          Screen shake is requested via the injected ScreenEffect object rather
          than being managed here.  This keeps Player decoupled from the
          rendering layer — the class doesn't need to know how shake is drawn,
          only that it should be requested.
        """
        self.lives -= 1
        _play(self._snd_fall)

        # Request screen shake (intensity 10, 40 frames ≈ 0.67 s)
        if self.screen_effect:
            self.screen_effect.shake(10, 40)

        if self.lives <= 0:
            self.alive = False

        # Brief upward knockback so the fall looks physical
        self.velocity_y = PLAYER_JUMP_FORCE * 0.5
        self.velocity_x = 0

    def collect_crystal(self) -> None:
        """
        Increment crystal count and play the pickup sound + glow effect.

        University report:
          Crystal collection is an event that has both a game-state consequence
          (incrementing the counter) and a visual/audio consequence.  The audio
          is triggered here; the visual glow is owned by GlowEffect and rendered
          by the level layer, so Player only needs to signal that collection
          occurred.
        """
        self.crystals += 1
        _play(self._snd_crystal)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def draw(self, surface: pygame.Surface, scroll_y: int = 0) -> None:
        """
        Blit the current sprite frame onto *surface*.

        Parameters
        ----------
        scroll_y : int
            The current level scroll offset (world-Y of the screen's top edge).
            Player.x / Player.y are stored in WORLD coordinates so that
            platform collision detection (which also uses world coords) is
            always consistent.  To convert to screen space we subtract
            scroll_y here at render time.

        Subclasses call super().draw(surface, scroll_y) then layer their own
        effects on top, also passing scroll_y so everything aligns.
        """
        # screen_y = world_y - scroll_y  (Pygame y-axis: 0 = top of screen)
        screen_x = int(self.x)
        screen_y = int(self.y) - scroll_y
        surface.blit(self._sprite, (screen_x, screen_y))
        if self._jump_dust_pending:
            if self.particle_system:
                self.particle_system.jump_dust((
                    int(self.x + self.SPRITE_WIDTH // 2),
                    int(self.y + self.SPRITE_HEIGHT - scroll_y),
                ))
            self._jump_dust_pending = False
        if self._landing_dust_pending:
            if self.particle_system:
                self.particle_system.landing_dust((
                    int(self.x + self.SPRITE_WIDTH // 2),
                    int(self.y + self.SPRITE_HEIGHT - scroll_y),
                ))
            self._landing_dust_pending = False

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def reset_position(self, x: float, y: float) -> None:
        """Teleport the player to (x, y) and zero velocity (used on respawn)."""
        self.x, self.y = float(x), float(y)
        self.velocity_x = self.velocity_y = 0.0
        self.on_ground  = False
        self._jump_dust_pending = False
        self._landing_dust_pending = False
        self.rect.topleft = (int(self.x), int(self.y))

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"x={self.x:.0f}, y={self.y:.0f}, "
            f"lives={self.lives}, crystals={self.crystals})"
        )


# ---------------------------------------------------------------------------
# LUNA
# ---------------------------------------------------------------------------

class Luna(Player):
    """
    Luna — balanced astronaut with crowd-control and defensive tools.

    Unique abilities
    ----------------
    double_jump   : One extra jump while airborne (two jumps total).
    speed_boost() : Temporarily raises move_speed for SPEED_BOOST_DURATION frames.
    use_special() : Activates ShieldBubble — blocks the next comet that hits Luna.

    University report:
      Luna's double-jump is the canonical example of a simple state machine:
        State A — on_ground          → first jump always available.
        State B — in air, 1 jump used → second jump available (flag True).
        State C — in air, 2 jumps used → no more jumps until landing resets flag.
      This is implemented with a single boolean (_can_double_jump) rather than
      a counter, keeping the logic easy to reason about.
    """

    # How long (frames) the speed boost lasts
    SPEED_BOOST_DURATION = 3 * 60   # 3 seconds at 60 FPS

    def __init__(self, x: float, y: float, controls: dict, screen_effect=None):
        super().__init__(
            x, y,
            sprite_path    = SPRITE_LUNA,
            controls       = controls,
            fallback_color = CYAN,
            screen_effect  = screen_effect,
        )
        # ---- Double-jump state ----
        self._can_double_jump: bool = False   # True while airborne with one jump remaining

        # ---- Speed-boost state ----
        self._boost_timer: int = 0            # frames remaining in current boost

        # ---- Shield (special) ----
        # ShieldBubble is composed in; it manages its own visual and active flag.
        self.shield = ShieldBubble()

        # ---- Shield cooldown ----
        self._shield_cooldown: int = 0        # frames until shield can be reactivated

    # ------------------------------------------------------------------
    # Overrides
    # ------------------------------------------------------------------

    def jump(self) -> None:
        """
        Luna's jump: standard first jump from ground, plus one mid-air jump.

        University report:
          When on the ground the first jump fires exactly like the base class.
          The _can_double_jump flag is SET to True at this point, not consumed.
          On the second call (while airborne), LUNA_DOUBLE_JUMP_FORCE is
          applied (slightly weaker than the first) and the flag is cleared so
          no further mid-air jumps are possible until landing.
          The flag is reset to False in _update_abilities() the moment
          on_ground becomes True, completing the state cycle.
        """
        if self.on_ground:
            # ---- First jump ----
            self.velocity_y   = PLAYER_JUMP_FORCE
            self.on_ground    = False
            self._can_double_jump = True    # arm the second jump
            self._jump_dust_pending = True
            _play(self._snd_jump)
        elif self._can_double_jump:
            # ---- Double jump ----
            # A slightly lower impulse gives a visually distinct shorter hop
            # so the player can tell it is the "bonus" jump.
            self.velocity_y       = LUNA_DOUBLE_JUMP_FORCE
            self._can_double_jump = False   # consume the second jump
            _play(self._snd_jump)

    def use_special(self) -> None:
        """
        Activate the ShieldBubble if the cooldown has expired.

        University report:
          ShieldBubble.activate() sets its internal active flag.  On each
          subsequent frame, Player.draw() renders the bubble around Luna.
          When a comet collides with Luna and shield.active is True, the
          game (level.py) calls shield.absorb() instead of take_damage(),
          and the bubble plays its burst animation before deactivating.
          The cooldown prevents Luna from re-shielding immediately after
          the bubble pops.
        """
        if self._shield_cooldown <= 0 and not self.shield.active:
            self.shield.activate()
            self._shield_cooldown = COOLDOWN_LUNA_SHIELD

    def speed_boost(self) -> None:
        """
        Temporarily raise move_speed by LUNA_SPEED_BOOST for 3 seconds.

        University report:
          move_speed is set once here; _update_abilities() counts down the
          timer and restores the original speed when it expires.  Using a
          frame-based timer (rather than a wall-clock timestamp) keeps the
          code deterministic and independent of system time.
        """
        if self._boost_timer <= 0:
            self.move_speed  = PLAYER_WALK_SPEED + LUNA_SPEED_BOOST
            self._boost_timer = self.SPEED_BOOST_DURATION

    def _update_abilities(self, keys) -> None:
        """
        Per-frame maintenance for Luna's timers.

        • Reset _can_double_jump when she touches the ground.
        • Count down speed-boost timer and restore base speed on expiry.
        • Count down shield cooldown.
        • Forward update to the ShieldBubble so it can animate.
        """
        # Reset double-jump availability on landing
        if self.on_ground:
            self._can_double_jump = False

        # Speed-boost countdown
        if self._boost_timer > 0:
            self._boost_timer -= 1
            if self._boost_timer == 0:
                # Restore base movement speed exactly (avoids float drift)
                self.move_speed = PLAYER_WALK_SPEED

        # Shield cooldown countdown
        if self._shield_cooldown > 0:
            self._shield_cooldown -= 1

        # Animate the shield bubble each frame (pulse + burst if absorbing)
        self.shield.update()

    def draw(self, surface: pygame.Surface, scroll_y: int = 0) -> None:
        """
        Draw Luna's sprite then overlay the shield bubble if active.

        The shield bubble must be positioned in SCREEN space so it renders
        centred on Luna's visible sprite.  self.center returns world coords,
        so we subtract scroll_y to convert to screen space before passing
        to ShieldBubble.draw().
        """
        super().draw(surface, scroll_y)
        # Convert Luna's world-space centre to screen space for the shield
        screen_center = (self.center[0], self.center[1] - scroll_y)
        # ShieldBubble.draw() only renders when self.shield.active is True
        self.shield.draw(surface, screen_center)

    @property
    def shield_ready(self) -> bool:
        """True if the shield can be activated right now."""
        return self._shield_cooldown <= 0 and not self.shield.active

    @property
    def shield_cooldown_pct(self) -> float:
        """Fraction of cooldown remaining (0.0 = ready, 1.0 = just used)."""
        return self._shield_cooldown / COOLDOWN_LUNA_SHIELD


# ---------------------------------------------------------------------------
# ORION
# ---------------------------------------------------------------------------

class Orion(Player):
    """
    Orion — high-jumping brute with platform manipulation abilities.

    Unique abilities
    ----------------
    jump()           : super jump — 1.8× normal jump force.
    magnet_pull()    : draws the nearest platform within ORION_MAGNET_RADIUS
                       a few pixels toward Orion, helping him reach distant ledges.
    use_special()    : freeze special — marks all nearby platforms as frozen
                       for ORION_FREEZE_DURATION frames; they glow blue
                       (via ScreenEffect.freeze_tint) and do not crumble.

    University report:
      Orion demonstrates how ability design can influence level layout.
      The magnet pull is not a physics simulation; it moves platform rects
      discretely (by a fixed number of pixels per activation) to keep the
      mechanic predictable and fair.  Platform objects expose a `frozen` flag
      that the level renderer checks each frame to apply the freeze tint.
    """

    # Pixels per frame the magnet nudges the nearest platform horizontally
    MAGNET_PULL_AMOUNT = 12

    def __init__(self, x: float, y: float, controls: dict, screen_effect=None):
        super().__init__(
            x, y,
            sprite_path    = SPRITE_ORION,
            controls       = controls,
            fallback_color = GOLD,
            screen_effect  = screen_effect,
        )
        # ---- Freeze state ----
        self._freeze_timer: int    = 0   # frames remaining in the freeze
        self._freeze_cooldown: int = 0   # frames until freeze can be used again
        self.frozen_platforms: list = [] # reference to platforms currently frozen

        # ---- Magnet cooldown ----
        self._magnet_cooldown: int = 0   # frames until magnet can be used again

    # ------------------------------------------------------------------
    # Overrides
    # ------------------------------------------------------------------

    def jump(self) -> None:
        """
        Orion's super jump: 1.8× the normal PLAYER_JUMP_FORCE.

        University report:
          ORION_SUPER_JUMP_FORCE is defined in config.py as a large negative
          value.  Because Orion can only jump from the ground (no double jump),
          the mechanic is easy to understand — press jump for a very high arc.
          The trade-off is that Orion cannot correct his trajectory mid-air,
          so platform positioning and player timing matter more.
        """
        if self.on_ground:
            self.velocity_y = ORION_SUPER_JUMP_FORCE
            self.on_ground  = False
            self._jump_dust_pending = True
            _play(self._snd_jump)

    def magnet_pull(self, platforms: list) -> None:
        """
        Pull the nearest platform within ORION_MAGNET_RADIUS toward Orion.

        University report:
          The nearest platform is found with a simple linear search comparing
          the Euclidean distance from Orion's centre to each platform's centre.
          Once found, the platform rect is nudged horizontally so that its
          centre moves one step closer to Orion's horizontal position.
          This is a deliberate simplification: a full physics-based attractor
          would be harder to balance for gameplay.
        """
        if self._magnet_cooldown > 0 or not platforms:
            return

        ox, oy = self.center
        nearest = None
        nearest_dist = float("inf")

        for plat in platforms:
            px = plat.rect.centerx
            py = plat.rect.centery
            dist = math.hypot(px - ox, py - oy)
            if dist < ORION_MAGNET_RADIUS and dist < nearest_dist:
                nearest      = plat
                nearest_dist = dist

        if nearest is not None:
            # Nudge the platform horizontally toward Orion
            if nearest.rect.centerx < ox:
                nearest.rect.x += self.MAGNET_PULL_AMOUNT
            else:
                nearest.rect.x -= self.MAGNET_PULL_AMOUNT

            # Brief cooldown to prevent spamming (half a second)
            self._magnet_cooldown = 30

    def use_special(self) -> None:
        """
        Freeze all platforms within ORION_MAGNET_RADIUS for ORION_FREEZE_DURATION frames.

        University report:
          Frozen platforms have two effects:
            1. Their `frozen` flag is set to True — the level renderer calls
               ScreenEffect.freeze_tint() on their rect each frame, painting
               a blue/cyan overlay.
            2. Crumbling platforms ignore player weight while frozen, so they
               don't crumble mid-freeze.
          After ORION_FREEZE_DURATION frames, _update_abilities() clears the
          flag on every platform that was frozen during this activation.
          Storing references in self.frozen_platforms (rather than searching
          each frame) ensures we can unfreeze exactly the platforms that were
          frozen, even if the player moves away.
        """
        if self._freeze_cooldown > 0:
            return

        self._freeze_timer    = ORION_FREEZE_DURATION
        self._freeze_cooldown = COOLDOWN_ORION_FREEZE
        self.frozen_platforms = []   # will be populated by level.py each frame,
                                     # or set from outside when platforms are known

    def freeze_nearby(self, platforms: list) -> None:
        """
        Called by level.py after use_special() to mark platforms as frozen.

        Parameters
        ----------
        platforms : list of all active platform objects.
        """
        ox, oy = self.center
        for plat in platforms:
            dist = math.hypot(plat.rect.centerx - ox, plat.rect.centery - oy)
            if dist <= ORION_MAGNET_RADIUS:
                plat.frozen = True
                if plat not in self.frozen_platforms:
                    self.frozen_platforms.append(plat)

    def _update_abilities(self, keys) -> None:
        """
        Per-frame maintenance for Orion's timers.

        • Count down freeze timer; unfreeze platforms on expiry.
        • Count down freeze cooldown.
        • Count down magnet cooldown.
        """
        # Freeze countdown
        if self._freeze_timer > 0:
            self._freeze_timer -= 1
            if self._freeze_timer == 0:
                # Thaw every platform that was frozen this cycle
                for plat in self.frozen_platforms:
                    plat.frozen = False
                self.frozen_platforms = []

        # Cooldown countdowns
        if self._freeze_cooldown > 0:
            self._freeze_cooldown -= 1
        if self._magnet_cooldown > 0:
            self._magnet_cooldown -= 1

    @property
    def freeze_active(self) -> bool:
        """True while the freeze special is currently running."""
        return self._freeze_timer > 0

    @property
    def freeze_cooldown_pct(self) -> float:
        """Fraction of cooldown remaining (0.0 = ready, 1.0 = just used)."""
        return self._freeze_cooldown / COOLDOWN_ORION_FREEZE


# ---------------------------------------------------------------------------
# NOVA
# ---------------------------------------------------------------------------

class Nova(Player):
    """
    Nova — the speedster; fastest movement and a trail that reveals secrets.

    Unique abilities
    ----------------
    move_speed    : 1.5× base speed at all times (no activation needed).
    use_special() : Activate SparkTrail — a golden trail that follows Nova
                    and, in Level 2, briefly reveals hidden platforms it
                    passes over.

    University report:
      Nova's speed advantage is implemented by setting move_speed in __init__
      rather than via a timed buff, reflecting a permanent character attribute.
      SparkTrail.emit() is called every frame Nova is moving so the trail
      always looks continuous.  get_reveal_rect() provides a bounding box
      that the level renderer uses to toggle hidden platforms visible.
    """

    SPEED_MULTIPLIER = 1.5   # Nova is 50 % faster than the base character

    def __init__(self, x: float, y: float, controls: dict, screen_effect=None):
        super().__init__(
            x, y,
            sprite_path    = SPRITE_NOVA,
            controls       = controls,
            fallback_color = PINK,
            screen_effect  = screen_effect,
        )
        # Apply permanent speed bonus
        self.move_speed = PLAYER_WALK_SPEED * self.SPEED_MULTIPLIER

        # ---- Spark trail (special) ----
        # SparkTrail is composed in and updated every frame she moves.
        self.spark_trail = SparkTrail()

        # ---- Spark trail state ----
        self._trail_active: bool  = False   # True while the trail is emitting
        self._trail_timer:  int   = 0       # frames remaining
        self._trail_cooldown: int = 0       # frames until special can be reused

        # ---- Dash state (special activation triggers a brief speed burst) ----
        self._dash_timer: int = 0           # frames remaining in current dash

    # ------------------------------------------------------------------
    # Overrides
    # ------------------------------------------------------------------

    def use_special(self) -> None:
        """
        Activate the SparkTrail for NOVA_SPARK_DURATION frames.

        University report:
          Activating the spark trail does two things:
            1. Sets _trail_active = True so emit() is called every update frame.
            2. Triggers a brief dash (NOVA_DASH_DURATION frames) where Nova's
               horizontal speed is temporarily NOVA_DASH_SPEED regardless of
               move_speed, giving a satisfying burst-of-movement feel when the
               ability fires.
          The trail's SparkTrail.get_reveal_rect() is polled by level.py each
          frame; any hidden platform whose rect intersects the reveal rect is
          temporarily marked as revealed.
        """
        if self._trail_cooldown > 0:
            return

        self._trail_active  = True
        self._trail_timer   = NOVA_SPARK_DURATION
        self._trail_cooldown = COOLDOWN_NOVA_DASH

        # Brief horizontal dash in the direction Nova is facing
        self._dash_timer = NOVA_DASH_DURATION

    def update(self, platforms: list, keys: pygame.key.ScancodeWrapper) -> None:
        """
        Nova's update also emits spark stamps while the trail is active and
        handles the dash velocity override.
        """
        # Override horizontal velocity during a dash
        if self._dash_timer > 0:
            direction = 1 if self.facing_right else -1
            self.velocity_x = direction * NOVA_DASH_SPEED
            self._dash_timer -= 1

        # Run base physics/input/collision
        super().update(platforms, keys)

        # Emit a trail stamp every frame while the trail is active and Nova moves
        if self._trail_active and abs(self.velocity_x) > 0.5:
            self.spark_trail.emit(self.center)

    def _update_abilities(self, keys) -> None:
        """
        Per-frame maintenance for Nova's timers.

        • Count down trail timer; deactivate and clear trail on expiry.
        • Count down trail cooldown.
        • Update SparkTrail stamps (ages + removes expired stamps).
        """
        if self._trail_timer > 0:
            self._trail_timer -= 1
            if self._trail_timer == 0:
                self._trail_active = False
                self.spark_trail.clear()

        if self._trail_cooldown > 0:
            self._trail_cooldown -= 1

        # Age spark trail stamps so they fade out correctly
        self.spark_trail.update()

    def draw(self, surface: pygame.Surface, scroll_y: int = 0) -> None:
        """
        Draw the spark trail beneath Nova's sprite, then draw Nova.

        Both the trail and the sprite need the same scroll_y offset so they
        render in the same screen space.  Trail is drawn first so Nova's
        sprite appears in front of it.
        """
        self.spark_trail.draw(surface, scroll_y)
        super().draw(surface, scroll_y)

    def get_reveal_rect(self) -> pygame.Rect | None:
        """
        Return the bounding rect of the active spark trail for platform reveal.

        The level renderer polls this each frame.  Returns None when the trail
        is inactive so the renderer knows no reveal is happening.
        """
        if self._trail_active:
            return self.spark_trail.get_reveal_rect()
        return None

    @property
    def trail_active(self) -> bool:
        """True while the spark trail special is running."""
        return self._trail_active

    @property
    def trail_cooldown_pct(self) -> float:
        """Fraction of cooldown remaining (0.0 = ready, 1.0 = just used)."""
        return self._trail_cooldown / COOLDOWN_NOVA_DASH


# ---------------------------------------------------------------------------
# FACTORY FUNCTION
# ---------------------------------------------------------------------------

def create_player(
    character_id: str,
    x: float,
    y: float,
    controls: dict,
    screen_effect=None,
) -> Player:
    """
    Instantiate the correct Player subclass for *character_id*.

    Parameters
    ----------
    character_id : str
        One of CHAR_LUNA, CHAR_NOVA, CHAR_ORION from config.py.
    x, y         : float
        Starting world position.
    controls     : dict
        CONTROLS_P1 or CONTROLS_P2 (defined at top of this module).
    screen_effect : ScreenEffect | None
        Injected by main.py for shake / flash requests.

    Returns
    -------
    Player
        The appropriate subclass instance, ready to update and draw.

    Raises
    ------
    ValueError
        If *character_id* does not match any known character.
    """
    mapping = {
        CHAR_LUNA:  Luna,
        CHAR_NOVA:  Nova,
        CHAR_ORION: Orion,
    }
    cls = mapping.get(character_id)
    if cls is None:
        raise ValueError(
            f"Unknown character_id '{character_id}'. "
            f"Expected one of: {list(mapping.keys())}"
        )
    return cls(x, y, controls=controls, screen_effect=screen_effect)
