"""
level.py — Moon Saviors
=======================
Contains all level logic, platform behaviour, comet hazards, and win/lose
conditions for both game levels.

Classes
-------
  Platform  — static or crumbling tile the players stand on
  Comet     — falling hazard that destroys platforms and damages players
  Level1    — fixed-layout Rescue Mission with moon crystal win condition
  Level2    — procedurally generated Endless Ascent with high-score tracking

University report note:
  Both Level classes follow a strict three-phase loop pattern used throughout
  the game:
      update(players, keys, screen_effect, particles) → mutate game state
      draw(surface)                                   → render current state
      get_events()                                    → return event strings
                                                        consumed by main.py
  This separation keeps rendering and logic independent, making each easier
  to test and extend.
"""

import pygame
import random
import math
import os

from config import (
    # Screen
    SCREEN_WIDTH, SCREEN_HEIGHT,
    # Physics / scroll
    SCROLL_SPEED, GRAVITY,
    # Platform geometry
    PLATFORM_WIDTH,
    # Comet
    COMET_SPEED_MIN, COMET_SPEED_MAX,
    COMET_SPAWN_INTERVAL, COMET_WIDTH, COMET_HEIGHT,
    COMET_INTERVAL_L2_MIN,
    L2_COMET_RAMP_HEIGHT, L2_COMET_RAMP_STEP,
    # Moonquake
    MOONQUAKE_INTERVAL, MOONQUAKE_SHAKE_MAGNITUDE,
    MOONQUAKE_SHAKE_DURATION, MOONQUAKE_PLATFORM_SHIFT,
    # Crystal
    CRYSTAL_Y_POSITION, CRYSTAL_FLASH_FRAMES, CRYSTAL_AURA_RADIUS,
    # Level 2
    L2_HIDDEN_PLATFORM_CHANCE,
    L2_SCORE_PER_PLATFORM,
    # Asset paths
    PLATFORM_STATIC, PLATFORM_CRUMBLING,
    FX_COMET, FX_COMET_EXPLOSION, FX_MOON_CRYSTAL,
    BG_LEVEL1, BG_LEVEL2,
    MUSIC_LEVEL1, MUSIC_LEVEL2,
    SFX_COMET_IMPACT, SFX_PLATFORM_CRUMBLE,
    SFX_MOONQUAKE, SFX_CRYSTAL_PICKUP, SFX_VICTORY, SFX_VOLUME,
    # Colours
    WHITE, BLACK, GREEN, CYAN, GOLD, PURPLE, PINK,
    COLOR_CRYSTAL, COLOR_FREEZE,
    # Character ID
    CHAR_NOVA,
    # FPS
    FPS,
)
from effects import ParticleSystem, ScreenEffect, GlowEffect


# ---------------------------------------------------------------------------
# CONSTANTS LOCAL TO THIS MODULE
# ---------------------------------------------------------------------------

PLATFORM_STATIC   = "STATIC"     # platform type identifier
PLATFORM_CRUMBLE  = "CRUMBLING"  # platform type identifier
PLATFORM_MOVING   = "MOVING"     # moving platform type identifier

# Shake amplitude (px) applied to crumbling platforms while they wobble
CRUMBLE_SHAKE_AMP = 7

# Cracked platforms begin warning shortly after a player lands, then break
# after a visible shake period.
CRUMBLE_WARN_FRAMES = 8
CRUMBLE_BREAK_FRAMES = FPS * 2

# Horizontal shift applied to each platform during a moonquake (signed random)
QUAKE_SHIFT_RANGE = MOONQUAKE_PLATFORM_SHIFT    # ± this many pixels


# Moving platform tuning
MOVING_PLATFORM_RANGE = 80
MOVING_PLATFORM_SPEED = 1.1

# ---------------------------------------------------------------------------
# ASSET HELPERS
# ---------------------------------------------------------------------------

def _load_image(path: str, size: tuple | None = None) -> pygame.Surface:
    """
    Load an image, scaling to *size* if provided.
    Returns a magenta fallback surface if the file is missing.
    """
    try:
        img = pygame.image.load(path).convert_alpha()
        if size:
            img = pygame.transform.smoothscale(img, size)
        return img
    except (FileNotFoundError, pygame.error):
        surf = pygame.Surface(size if size else (64, 64), pygame.SRCALPHA)
        surf.fill((255, 0, 255, 180))
        return surf


def _load_sound(path: str) -> pygame.mixer.Sound | None:
    """Load a sound; return None silently if file is missing."""
    try:
        snd = pygame.mixer.Sound(path)
        snd.set_volume(SFX_VOLUME)
        return snd
    except (FileNotFoundError, pygame.error):
        return None


def _play(sound) -> None:
    """Play *sound* if it loaded successfully."""
    if sound:
        sound.play()


def _start_music(path: str, volume: float = 0.6) -> None:
    """
    Stream background music from *path*.
    Silently skips if the file is missing or mixer is unavailable.
    """
    try:
        pygame.mixer.music.load(path)
        pygame.mixer.music.set_volume(volume)
        pygame.mixer.music.play(-1)   # -1 = loop forever
    except (FileNotFoundError, pygame.error):
        pass


# ---------------------------------------------------------------------------
# PLATFORM
# ---------------------------------------------------------------------------

# Module-level cache — each unique (path, width, height) is only processed once
_PLATFORM_IMG_CACHE: dict = {}

def _load_platform_img(path: str, display_width: int, display_height: int) -> pygame.Surface:
    """
    Load a platform PNG, crop out black padding, and return a display-ready surface.

    The platform PNGs are large squares with a black (0,0,0) background and no
    alpha channel. The stone graphic sits in a band starting roughly 57% down
    the image. This function:
      1. Scans row-average brightness to find where content starts.
      2. Crops only the top-face texture rows (first 12% of content band).
      3. Blits the scaled face texture onto a transparent result surface.
    Result: only the platform art is visible; the collision area stays hidden.
    """
    cache_key = (path, display_width, display_height)
    if cache_key in _PLATFORM_IMG_CACHE:
        return _PLATFORM_IMG_CACHE[cache_key]

    SAMPLE_STEP         = 8
    CONTENT_THRESH      = 6
    TEXTURE_ROWS_PCT    = 0.12
    try:
        raw = pygame.image.load(path)
        w, h = raw.get_size()

        # Find first content row by row-average brightness
        first_content_row = h // 2
        for y in range(h):
            total = sum(
                raw.get_at((x, y))[0] + raw.get_at((x, y))[1] + raw.get_at((x, y))[2]
                for x in range(0, w, SAMPLE_STEP)
            )
            avg = total / (3 * max(1, w // SAMPLE_STEP))
            if avg > CONTENT_THRESH:
                first_content_row = y
                break

        content_h = h - first_content_row
        face_h    = max(8, int(content_h * TEXTURE_ROWS_PCT))
        face_crop = raw.subsurface(pygame.Rect(0, first_content_row, w, face_h))

        result = pygame.Surface((display_width, display_height), pygame.SRCALPHA)

        face_display_h = min(display_height, max(6, display_height // 2))
        face_scaled    = pygame.transform.smoothscale(face_crop, (display_width, face_display_h))
        face_scaled    = face_scaled.convert_alpha()
        face_scaled.lock()
        for py in range(face_scaled.get_height()):
            for px in range(face_scaled.get_width()):
                r, g, b, a = face_scaled.get_at((px, py))
                if a == 0 or (r <= 12 and g <= 12 and b <= 12):
                    face_scaled.set_at((px, py), (r, g, b, 0))
        face_scaled.unlock()
        result.blit(face_scaled, (0, 0))

        final = result.convert_alpha()
        _PLATFORM_IMG_CACHE[cache_key] = final
        return final

    except (FileNotFoundError, pygame.error):
        surf = pygame.Surface((display_width, display_height), pygame.SRCALPHA)
        pygame.draw.rect(surf, (90, 100, 115), (0, 0, display_width, min(10, display_height)))
        _PLATFORM_IMG_CACHE[cache_key] = surf
        return surf


class Platform:
    """
    A single platform tile.

    Two types are supported:
      STATIC    — indestructible; players land on it indefinitely.
      CRUMBLING — shakes after a player stands on it for CRUMBLE_WARN_FRAMES
                  frames, then breaks apart with a particle explosion.

    Attributes exposed for external logic
    --------------------------------------
    rect    : pygame.Rect  — current collision & draw rectangle.
    frozen  : bool         — True while Orion's freeze special is active.
                             Crumbling timer is paused while frozen.
    hidden  : bool         — True for Level 2 ghost platforms (Nova reveal).
    revealed: bool         — True once Nova's spark trail has uncovered it.
    broken  : bool         — True once a crumbling platform has disintegrated;
                             the level removes it from the active list.

    University report — crumble state machine:
      State 0 (IDLE)      → player not on platform
      State 1 (CRUMBLING) → player on platform; shake timer counting up
      State 2 (BROKEN)    → timer exceeded CRUMBLE_WARN_FRAMES; broken=True
    """

    def __init__(self, x: int, y: int,
                 kind: str = PLATFORM_STATIC,
                 width: int = PLATFORM_WIDTH,
                 hidden: bool = False,
                 move_axis: str = "horizontal",
                 move_range: int = MOVING_PLATFORM_RANGE,
                 move_speed: float = MOVING_PLATFORM_SPEED):

        self.kind   = kind
        self.hidden = hidden       # invisible until revealed (Level 2)
        self.revealed  = False     # becomes True when Nova's trail passes over
        self.reveal_timer = 0      # frames of visibility remaining after reveal

        self.frozen = False        # True while Orion's freeze special is active
        self.broken = False        # True after crumbling platform shatters
        self.delta_x = 0
        self.delta_y = 0

        # ---- Crumble state ----
        self._crumble_timer: int  = 0     # frames player has stood here
        self._crumbling: bool     = False  # True during the shake warning phase
        self._shake_offset: int   = 0     # pixel shake applied this frame

        # ---- Moving-platform state ----
        self._move_axis = move_axis
        self._move_range = move_range
        self._move_speed = move_speed
        self._move_dir = random.choice([-1, 1])
        self._origin_x = float(x)
        self._origin_y = float(y)
        self._move_x = float(x)
        self._move_y = float(y)

        # ---- Visuals ----
        if kind == PLATFORM_CRUMBLE:
            self._visual_h = 52
            self._img = _load_platform_img(from_config_PLATFORM_CRUMBLING, width, self._visual_h)
        else:
            self._visual_h = 36
            self._img = _load_platform_img(from_config_PLATFORM_STATIC, width, self._visual_h)

        self.rect = pygame.Rect(x, y, width, self._visual_h)

        # ---- Sound ----
        self._snd_crumble = _load_sound(SFX_PLATFORM_CRUMBLE)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def on_player_land(self) -> None:
        """
        Called by Player._resolve_platform_collisions() each frame a player
        is standing on this tile.

        University report:
          Incrementing _crumble_timer here (rather than in update()) ties the
          crumble countdown directly to player contact.  If the player jumps
          off and re-lands the timer keeps counting; there is no reset on
          leaving — this is a deliberate design choice to penalise hesitation.
        """
        if self.kind == PLATFORM_CRUMBLE and not self.frozen:
            self._crumble_timer += 1
            if self._crumble_timer >= CRUMBLE_WARN_FRAMES:
                self._crumbling = True

    def update(self, particles: ParticleSystem) -> None:
        """
        Advance crumbling animation and break the platform when the timer
        is fully exhausted.

        Parameters
        ----------
        particles : ParticleSystem
            Used to spawn a debris explosion when the platform breaks.
        """
        if self.broken:
            return

        self.delta_x = 0
        self.delta_y = 0

        if self.kind == PLATFORM_MOVING and not self.frozen:
            self._update_movement()

        # ---- Shake warning animation ----
        if self.kind == PLATFORM_CRUMBLE and self._crumbling:
            # Oscillate the draw offset so the platform visually rattles.
            # Using the timer modulo gives a repeating left-right pattern.
            self._shake_offset = CRUMBLE_SHAKE_AMP if (self._crumble_timer // 2) % 2 == 0 else -CRUMBLE_SHAKE_AMP
            self._crumble_timer += 1

            # ---- Break condition ----
            # Give the player a short warning after shaking starts
            # before the platform actually disappears.
            if self._crumble_timer >= CRUMBLE_WARN_FRAMES + CRUMBLE_BREAK_FRAMES:
                self._break(particles)

        # ---- Reveal timer countdown (Level 2 hidden platforms) ----
        if self.revealed and self.reveal_timer > 0:
            self.reveal_timer -= 1
            if self.reveal_timer == 0:
                self.revealed = False   # goes dark again

    def _update_movement(self) -> None:
        """Move this platform inside its configured horizontal/vertical range."""
        old_x, old_y = self.rect.x, self.rect.y

        if self._move_axis == "vertical":
            self._move_y += self._move_dir * self._move_speed
            min_y = self._origin_y - self._move_range
            max_y = self._origin_y + self._move_range
            if self._move_y < min_y or self._move_y > max_y:
                self._move_y = max(min_y, min(max_y, self._move_y))
                self._move_dir *= -1
            self.rect.y = int(round(self._move_y))
        else:
            self._move_x += self._move_dir * self._move_speed
            min_x = self._origin_x - self._move_range
            max_x = self._origin_x + self._move_range
            if self._move_x < min_x or self._move_x > max_x:
                self._move_x = max(min_x, min(max_x, self._move_x))
                self._move_dir *= -1
            self.rect.x = int(round(self._move_x))

        self.rect.x = max(0, min(SCREEN_WIDTH - self.rect.width, self.rect.x))
        self._move_x = float(self.rect.x)
        self._move_y = float(self.rect.y)
        self.delta_x = self.rect.x - old_x
        self.delta_y = self.rect.y - old_y

    def shift_horizontal(self, amount: int) -> None:
        """Move the platform and its movement bounds horizontally."""
        old_x = self.rect.x
        self.rect.x = max(0, min(SCREEN_WIDTH - self.rect.width, self.rect.x + amount))
        applied = self.rect.x - old_x
        self._origin_x += applied
        self._move_x = float(self.rect.x)

    def _break(self, particles: ParticleSystem) -> None:
        """
        Shatter this platform: play sound, spawn debris particles, set broken.

        University report:
          Spawning particles at the centre of the rect ties the visual effect
          to the platform's current (possibly shifted) position.  The platform
          is then flagged broken=True; the level's update loop removes all
          broken platforms from self.platforms in the same frame, so no
          collision check ever sees a broken platform.
        """
        _play(self._snd_crumble)
        if particles:
            particles.comet_impact(self.rect.center)   # reuse explosion emitter
        self.broken = True

    def reveal(self, duration: int) -> None:
        """Make a hidden platform visible for *duration* frames."""
        self.revealed     = True
        self.reveal_timer = max(self.reveal_timer, duration)  # extend if already revealed

    def draw(self, surface: pygame.Surface, scroll_y: int = 0) -> None:
        """
        Render the platform, applying shake offset and scroll offset.

        Parameters
        ----------
        scroll_y : int
            Vertical world-scroll amount subtracted from world y coordinates
            to convert to screen space.  Passed from the level each frame.
        """
        if self.broken:
            return

        # Hidden platforms that are not yet revealed are invisible
        if self.hidden and not self.revealed:
            return

        draw_x = self.rect.x + self._shake_offset
        draw_y = self.rect.y - scroll_y

        # Partially transparent if revealed but fading (last 30 frames)
        alpha = 255
        if self.hidden and self.revealed and self.reveal_timer < 30:
            alpha = int(255 * self.reveal_timer / 30)

        if alpha < 255:
            img_copy = self._img.copy()
            img_copy.set_alpha(alpha)
            surface.blit(img_copy, (draw_x, draw_y))
        else:
            surface.blit(self._img, (draw_x, draw_y))

        # ---- Freeze tint overlay ----
        # If Orion's freeze special is active, paint a cyan overlay over the
        # platform to signal that it is locked in place.
        if self.frozen:
            tint = pygame.Surface((self.rect.width, self._visual_h), pygame.SRCALPHA)
            tint.fill((*COLOR_FREEZE, 100))
            surface.blit(tint, (draw_x, draw_y))

        if self.kind == PLATFORM_MOVING:
            marker = pygame.Rect(draw_x + 8, draw_y + 4, max(6, self.rect.width - 16), 3)
            pygame.draw.rect(surface, CYAN, marker)


# Patch the class: it references module-level names we haven't set yet.
# We set them here after the class so the import at top of file is clean.
from config import PLATFORM_STATIC as _PS_PATH, PLATFORM_CRUMBLING as _PC_PATH
from_config_PLATFORM_STATIC    = _PS_PATH
from_config_PLATFORM_CRUMBLING = _PC_PATH


# ---------------------------------------------------------------------------
# COMET
# ---------------------------------------------------------------------------

class Comet:
    """
    A falling hazard that originates above the visible screen and descends
    at a random speed and angle.

    Behaviour on impact
    -------------------
    • Platform hit → destroy platform, spawn ParticleSystem explosion.
    • Player hit   → call player.take_damage() (unless Luna's shield absorbs it).

    University report — angle simulation:
      A small horizontal velocity component (vx) is added alongside the main
      downward velocity (vy), giving the comet a slight diagonal path.  This
      makes them harder to dodge than a purely vertical drop and adds visual
      variety without requiring a full physics simulation.
    """

    def __init__(self, scroll_y: int = 0):
        """
        Spawn a comet at a random x position just above the visible screen.

        Parameters
        ----------
        scroll_y : int
            Current world-scroll offset; used to place the comet in world
            space just above what is currently visible.
        """
        self.x = float(random.randint(20, SCREEN_WIDTH - COMET_WIDTH - 20))
        # Spawn just above the top of the screen in world space
        self.y = float(scroll_y - COMET_HEIGHT - random.randint(10, 60))

        speed  = random.uniform(COMET_SPEED_MIN, COMET_SPEED_MAX)
        # Slight horizontal drift (up to ±1.5 px/frame)
        self.vx = random.uniform(-1.5, 1.5)
        self.vy = speed

        self.rect   = pygame.Rect(int(self.x), int(self.y), COMET_WIDTH, COMET_HEIGHT)
        self.active = True   # False once the comet has hit something

        # ---- Visuals ----
        self._img = _load_image(FX_COMET, (COMET_WIDTH, COMET_HEIGHT))

        # ---- Sound ----
        self._snd_impact = _load_sound(SFX_COMET_IMPACT)

        # Rotation angle for the comet sprite (visual only, not physics)
        self._angle: float = math.degrees(math.atan2(self.vy, self.vx))

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(
        self,
        platforms: list,
        players: list,
        particles: ParticleSystem,
        scroll_y: int = 0,
    ) -> None:
        """
        Move the comet and check for collisions with platforms and players.

        Collision priority: platforms first, then players.  If a platform is
        hit the comet is destroyed before it can also hit a player.

        Parameters
        ----------
        platforms  : list of Platform objects currently active in the level.
        players    : list of Player objects (up to 2).
        particles  : ParticleSystem to receive the explosion on impact.
        scroll_y   : int  current vertical scroll offset for screen conversion.
        """
        if not self.active:
            return

        self.x += self.vx
        self.y += self.vy
        self.rect.x = int(self.x)
        self.rect.y = int(self.y)

        # Screen-space rect (for collision with players and platforms drawn
        # in screen coordinates)
        screen_rect = pygame.Rect(
            self.rect.x, self.rect.y - scroll_y,
            COMET_WIDTH, COMET_HEIGHT,
        )

        if particles:
            trail_x = int(screen_rect.centerx - self.vx * 8)
            trail_y = int(screen_rect.centery - self.vy * 6)
            particles.comet_trail((trail_x, trail_y))

        # ---- Platform collision ----
        for plat in platforms:
            if plat.broken:
                continue
            plat_screen = pygame.Rect(
                plat.rect.x, plat.rect.y - scroll_y,
                plat.rect.width, plat.rect.height,
            )
            if screen_rect.colliderect(plat_screen):
                self._impact(particles, screen_rect.center)
                plat.broken = True   # destroy the platform immediately
                return               # comet consumed; skip player checks

        # ---- Player collision ----
        for player in players:
            if not player.alive:
                continue
            # Compare in world space: both self.rect and player.rect use world
            # coordinates, so no screen conversion is needed here.
            if self.rect.colliderect(player.rect):
                # Check if Luna's shield intercepts the hit
                if (
                    hasattr(player, "shield")
                    and player.shield.active
                ):
                    # Shield absorbs the comet — bubble pops, player safe
                    player.shield.absorb()
                    self._impact(particles, (int(self.x), int(self.y) - scroll_y))
                else:
                    player.take_damage()
                    self._impact(particles, (int(self.x), int(self.y) - scroll_y))
                return

        # ---- Off-screen removal ----
        # Deactivate if the comet has fallen below the bottom of the screen.
        if self.rect.y - scroll_y > SCREEN_HEIGHT + 40:
            self.active = False

    def _impact(self, particles: ParticleSystem, pos: tuple) -> None:
        """
        Trigger the comet-impact visual and audio, then deactivate self.

        University report:
          Passing *pos* (screen space) rather than world space ensures the
          particle explosion appears where the player sees the comet hit,
          not offset by scroll_y.
        """
        _play(self._snd_impact)
        if particles:
            particles.comet_impact(pos)
        self.active = False

    # ------------------------------------------------------------------
    # Draw
    # ------------------------------------------------------------------

    def draw(self, surface: pygame.Surface, scroll_y: int = 0) -> None:
        """Blit the comet sprite at its current screen position."""
        if not self.active:
            return

        screen_x = int(self.x)
        screen_y = int(self.y) - scroll_y

        # Rotate sprite to align with direction of travel
        rotated = pygame.transform.rotate(self._img, -self._angle + 90)
        r = rotated.get_rect(center=(
            screen_x + COMET_WIDTH  // 2,
            screen_y + COMET_HEIGHT // 2,
        ))
        surface.blit(rotated, r.topleft)


# ---------------------------------------------------------------------------
# SHARED RESPAWN HELPER
# ---------------------------------------------------------------------------

def _respawn_on_screen(player, platforms, scroll_y: int) -> None:
    """
    Put a fallen player back on a platform that is currently visible on screen.

    The old behaviour respawned at a FIXED world position (the bottom starting
    platform).  Once the camera had scrolled away from it that position was
    below the screen, so the player fell again immediately and lost every life
    in a couple of seconds (a death-spiral).  This instead finds the highest
    platform inside the visible band and drops the player on top of it,
    centred; if somehow none is visible it places the player in the upper third
    of the current view so they always land back in play.
    """
    top    = scroll_y + 60
    bottom = scroll_y + SCREEN_HEIGHT - 120
    visible = [
        p for p in platforms
        if not p.broken
        and not (getattr(p, "hidden", False) and not getattr(p, "revealed", False))
        and top <= p.rect.top <= bottom
    ]
    if visible:
        plat = min(visible, key=lambda p: p.rect.top)   # highest visible ledge
        x = plat.rect.centerx - player.SPRITE_WIDTH // 2
        y = plat.rect.top - player.SPRITE_HEIGHT
    else:
        x = SCREEN_WIDTH // 2 - player.SPRITE_WIDTH // 2
        y = scroll_y + SCREEN_HEIGHT // 3
    player.reset_position(x, y)


# ---------------------------------------------------------------------------
# LEVEL 1 — RESCUE MISSION
# ---------------------------------------------------------------------------

def _carry_players_on_moving_platforms(players, platforms) -> None:
    """Move grounded players with platforms that shifted this frame."""
    for player in players:
        if not getattr(player, "alive", False) or not getattr(player, "on_ground", False):
            continue

        for plat in platforms:
            dx = getattr(plat, "delta_x", 0)
            dy = getattr(plat, "delta_y", 0)
            if dx == 0 and dy == 0:
                continue
            if getattr(plat, "hidden", False) and not getattr(plat, "revealed", False):
                continue

            old_top = plat.rect.top - dy
            horizontally_over_platform = (
                player.rect.right > plat.rect.left and
                player.rect.left < plat.rect.right
            )
            was_on_platform = abs(player.rect.bottom - old_top) <= 8
            is_on_platform = abs(player.rect.bottom - plat.rect.top) <= 8
            if horizontally_over_platform and (was_on_platform or is_on_platform):
                player.x += dx
                player.y += dy
                player.rect.x = int(player.x)
                player.rect.y = int(player.y)
                break


class Level1:
    """
    Fixed-layout rescue mission.

    Layout
    ------
    A predefined set of platforms is placed in world space.  The screen
    scrolls upward automatically (scroll_y increases each frame).  At the
    very top sits the moon crystal; touching it ends the level in victory.

    Events
    ------
    • Comets spawn at random intervals between 3 and 6 seconds.
    • A moonquake fires every MOONQUAKE_INTERVAL frames.
    • Both players must collect the crystal to win.

    University report — scroll-based level design:
      World coordinates are stored in absolute pixel values (y increases
      downward).  Every draw call subtracts the current scroll_y from world y
      to obtain screen y.  Only the scroll_y value changes each frame; the
      underlying platform positions never move unless a moonquake fires.
      This keeps collision detection independent of scroll speed.
    """

    # Total height of the level world (pixels)
    WORLD_HEIGHT = 4000

    def __init__(self, screen_effect: ScreenEffect):
        self.screen_effect = screen_effect
        self.particles     = ParticleSystem()
        self.glow          = GlowEffect()

        # ---- Scroll ----
        # scroll_y represents the world y of the top of the screen.
        # Starts at the bottom of the world so the player begins at the base.
        self.scroll_y: int = self.WORLD_HEIGHT - SCREEN_HEIGHT

        # ---- State ----
        self.won:       bool = False    # True once win condition is met
        self.events:    list = []       # strings consumed by main.py each frame
        self._win_timer: int = 0        # frames into the win animation

        # ---- Moonquake ----
        self._quake_timer: int = MOONQUAKE_INTERVAL
        self._snd_quake        = _load_sound(SFX_MOONQUAKE)
        self._snd_victory      = _load_sound(SFX_VICTORY)

        # ---- Comets ----
        self.comets: list[Comet]        = []
        self._comet_timer: int          = random.randint(5 * FPS, 9 * FPS)

        # ---- Crystal ----
        # Placed at the top of the world, centred horizontally
        self._crystal_world_y = CRYSTAL_Y_POSITION
        self._crystal_rect    = pygame.Rect(
            SCREEN_WIDTH // 2 - 18,
            self._crystal_world_y,
            36, 36,
        )
        self._crystal_collected = False
        self._crystal_img       = _load_image(FX_MOON_CRYSTAL, (36, 36))

        # ---- Background ----
        self._bg = _load_image(BG_LEVEL1, (SCREEN_WIDTH, SCREEN_HEIGHT))

        # ---- Build platforms ----
        self.platforms: list[Platform] = []
        self._build_platforms()

        # ---- Music ----
        _start_music(MUSIC_LEVEL1)

    # ------------------------------------------------------------------
    # Platform layout
    # ------------------------------------------------------------------

    def _build_platforms(self) -> None:
        """
        Generate a fixed set of platforms spread across the world height.

        University report — layout algorithm:
          Platforms are placed at evenly distributed world-y positions,
          with horizontal positions randomised within left/centre/right
          thirds of the screen.  Every 5th platform is a crumbling type
          to provide consistent challenge without making the level feel
          unfair.  A large starting platform at the bottom ensures both
          players always have somewhere safe to land on entry.
        """
        # ---- Starting platform (wide, at the bottom of the world) ----
        # Full-width starting platform so both players always land on it
        self._start_platform_y = self.WORLD_HEIGHT - 80
        self.platforms.append(Platform(
            0,
            self._start_platform_y,
            PLATFORM_STATIC,
            width=SCREEN_WIDTH,
        ))

        # ---- Generate intermediate platforms ----
        # A dense, well-aligned ladder of platforms so both players always have
        # a comfortably reachable ledge above them (no pixel-perfect jumps).
        num_platforms = 44
        y_step        = (self.WORLD_HEIGHT - 200) // num_platforms
        x_zones = [
            (30, SCREEN_WIDTH // 3 - PLATFORM_WIDTH),          # left zone
            (SCREEN_WIDTH // 3, 2 * SCREEN_WIDTH // 3 - PLATFORM_WIDTH),  # centre
            (2 * SCREEN_WIDTH // 3, SCREEN_WIDTH - PLATFORM_WIDTH - 30),  # right zone
        ]

        prev_zone = 1   # start in centre so first platform is reachable
        for i in range(num_platforms):
            world_y = self.WORLD_HEIGHT - 160 - i * y_step + random.randint(-20, 20)

            # Move at most ONE zone left/right each step (clamped, never
            # wrapping) so consecutive platforms are always within a single
            # jump horizontally — no impossible cross-screen leaps.
            zone_idx = max(0, min(2, prev_zone + random.choice([-1, 0, 1])))
            prev_zone = zone_idx
            x_min, x_max = x_zones[zone_idx]
            x = random.randint(x_min, max(x_min, x_max))

            # Keep most platforms stable, with occasional cracked/moving ones
            # to add variety without breaking the main route.
            if i % 11 == 5:
                kind = PLATFORM_MOVING
            elif i % 7 == 6:
                kind = PLATFORM_CRUMBLE
            else:
                kind = PLATFORM_STATIC
            self.platforms.append(Platform(
                x,
                world_y,
                kind,
                move_axis=random.choice(["horizontal", "vertical"]),
                move_range=random.randint(45, 80),
                move_speed=random.uniform(0.8, 1.2),
            ))

        # ---- Top platform (goal) ----
        self.platforms.append(Platform(
            SCREEN_WIDTH // 2 - 60,
            self._crystal_world_y + 50,
            PLATFORM_STATIC,
            width=120,
        ))

    # ------------------------------------------------------------------
    # Main loop methods
    # ------------------------------------------------------------------

    def update(self, players: list, keys) -> None:
        """
        Advance the level simulation by one frame.

        Order of operations:
          1. Scroll the world upward.
          2. Update platform crumble timers; remove broken ones.
          3. Spawn and update comets.
          4. Check moonquake timer.
          5. Check crystal collection (win condition).
          6. Update particle and glow effects.
          7. Tell players about frozen platforms (Orion ability).

        Parameters
        ----------
        players : list of Player instances.
        keys    : pygame.key.get_pressed() result (unused here, passed through).
        """
        self.events.clear()

        if self.won:
            self._update_win_animation(players)
            return

        # ---- 1. Scroll (player-following camera) ----
        # The camera follows the highest-climbing alive player, keeping them in
        # the upper third of the screen.  It only ever moves UP (it never shoves
        # a player off the bottom) and stops once the crystal is in view.  This
        # replaces the old fixed timed auto-scroll, which forced players to
        # climb faster than the layout allowed and made the level unfair.
        top_limit = max(0, self._crystal_world_y - SCREEN_HEIGHT // 4)
        target = self.scroll_y
        for p in players:
            if p.alive:
                target = min(target, p.y - SCREEN_HEIGHT // 3)
        target = max(top_limit, target)
        self.scroll_y = int(self.scroll_y + (target - self.scroll_y) * 0.08)

        # ---- 2. Platforms ----
        for plat in self.platforms:
            plat.update(self.particles)
        _carry_players_on_moving_platforms(players, self.platforms)
        self.platforms = [p for p in self.platforms if not p.broken]

        # Notify Orion if his freeze is active — freeze nearby platforms
        for player in players:
            if hasattr(player, "freeze_active") and player.freeze_active:
                player.freeze_nearby(self.platforms)

        # ---- 3. Comets ----
        self._comet_timer -= 1
        if self._comet_timer <= 0:
            self.comets.append(Comet(self.scroll_y))
            self._comet_timer = random.randint(5 * FPS, 9 * FPS)

        for comet in self.comets:
            comet.update(self.platforms, players, self.particles, self.scroll_y)
        self.comets = [c for c in self.comets if c.active]

        # ---- 4. Moonquake ----
        self._quake_timer -= 1
        if self._quake_timer <= 0:
            self._trigger_moonquake()

        # ---- 5. Win condition ----
        self._check_crystal(players)

        # ---- 6. Effects ----
        self.particles.update()
        self.glow.update()

        # ---- 7. Player falls below scroll region → damage + safe respawn ----
        for player in players:
            if player.alive and player.y > self.scroll_y + SCREEN_HEIGHT + 60:
                player.take_damage()
                if player.alive:
                    _respawn_on_screen(player, self.platforms, self.scroll_y)

    def _trigger_moonquake(self) -> None:
        """
        Fire the moonquake event: screen shake, platform shift, sound.

        University report:
          Platforms are shifted by a random amount in [-QUAKE_SHIFT_RANGE,
          +QUAKE_SHIFT_RANGE] horizontally.  Each platform gets an independent
          random value so the layout becomes irregular, forcing players to
          re-assess their route.  The shift is clamped so platforms never
          leave the screen entirely.
        """
        _play(self._snd_quake)
        self.screen_effect.shake(MOONQUAKE_SHAKE_MAGNITUDE, MOONQUAKE_SHAKE_DURATION)
        self.screen_effect.flash(PURPLE, 20)

        for plat in self.platforms:
            shift = random.randint(-QUAKE_SHIFT_RANGE, QUAKE_SHIFT_RANGE)
            plat.shift_horizontal(shift)

        self._quake_timer = MOONQUAKE_INTERVAL
        self.events.append("MOONQUAKE")

    def _check_crystal(self, players: list) -> None:
        """
        Win if any alive player's rect overlaps the crystal in screen space.

        University report:
          The crystal is tested in screen space (subtract scroll_y) so the
          collision stays consistent regardless of scroll position.
          Both players touching it triggers victory; a single player touching
          it also counts (accommodating situations where one player has died).
        """
        if self._crystal_collected:
            return

        crystal_screen = pygame.Rect(
            self._crystal_rect.x,
            self._crystal_rect.y - self.scroll_y,
            36, 36,
        )

        for player in players:
            if player.alive and player.rect.colliderect(crystal_screen):
                self._crystal_collected = True
                player.collect_crystal()
                self.screen_effect.flash(WHITE, CRYSTAL_FLASH_FRAMES)
                _play(self._snd_victory)
                self.won = True
                self._win_timer = 0
                self.events.append("WIN")
                return

    def _update_win_animation(self, players: list) -> None:
        """
        Emit green crystal-aura particles around the crystal for the win sequence.
        main.py reads the WIN event and transitions state after a short delay.
        """
        self._win_timer += 1
        self.particles.crystal_aura((
            self._crystal_rect.centerx,
            self._crystal_rect.centery - self.scroll_y,
        ))
        self.particles.update()
        self.glow.update()

    # ------------------------------------------------------------------
    # Draw
    # ------------------------------------------------------------------

    def draw(self, surface: pygame.Surface) -> None:
        """
        Render background, platforms, crystal, comets, and particles.

        Draw order (back to front):
          1. Background
          2. Platforms (including freeze tint)
          3. Crystal + glow
          4. Comets
          5. Particles
          6. Screen flash (outermost layer)
        """
        # ---- 1. Background — tile vertically to fill any scroll position ----
        bg_h  = self._bg.get_height()
        start = -(self.scroll_y % bg_h)
        y     = start
        while y < SCREEN_HEIGHT:
            surface.blit(self._bg, (0, y))
            y += bg_h

        # ---- 2. Platforms ----
        for plat in self.platforms:
            plat.draw(surface, self.scroll_y)

        # ---- 3. Crystal + glow ----
        if not self._crystal_collected:
            crystal_screen_y = self._crystal_rect.y - self.scroll_y
            self.glow.draw(surface, (self._crystal_rect.centerx, crystal_screen_y + 18))

        # ---- 4. Comets ----
        for comet in self.comets:
            comet.draw(surface, self.scroll_y)

        # ---- 5. Particles ----
        self.particles.draw(surface)

        # ---- 6. Flash (drawn last so it covers everything) ----
        self.screen_effect.draw_flash(surface)

    def get_events(self) -> list:
        """Return and clear the event queue for this frame."""
        evts = self.events[:]
        self.events.clear()
        return evts


# ---------------------------------------------------------------------------
# LEVEL 2 — ENDLESS ASCENT
# ---------------------------------------------------------------------------

class Level2:
    """
    Procedurally generated endless vertical platformer.

    Key differences from Level 1
    ----------------------------
    • Platforms are generated ahead of the player as they climb (never a
      fixed set).
    • L2_HIDDEN_PLATFORM_CHANCE % of platforms are hidden (alpha=0) until
      Nova's spark trail passes over them.
    • Comet spawn rate increases every L2_COMET_RAMP_HEIGHT pixels of height.
    • There is no win condition — the level runs until both players are dead.
    • A height-based score is tracked and compared against the high score.

    University report — procedural generation:
      Platforms are generated in a rolling window: when the highest existing
      platform is within GEN_LOOKAHEAD pixels of the top of the screen, a new
      platform is appended above it.  The horizontal position alternates
      between left, centre, and right thirds with slight randomness so the
      layout is always navigable but never predictable.  This is a minimal
      implementation of wave-function collapse's simpler cousin — constrained
      random placement.
    """

    # How many pixels above the screen top we generate platforms up to.
    # Generous lookahead keeps the visible field full of platforms to aim for.
    GEN_LOOKAHEAD = 900

    def __init__(self, screen_effect: ScreenEffect):
        self.screen_effect = screen_effect
        self.particles     = ParticleSystem()

        # ---- Scroll ----
        # In Level 2 scroll_y tracks the world y of the top of the screen.
        # The world is infinite upward; we generate platforms on demand.
        self.scroll_y: int = 0          # starts at top; we generate downward

        # Actually, for Level 2 we anchor so that scroll_y is the world-y
        # of the screen's TOP edge.  Larger scroll_y = further up the world.
        # We begin with the player near the bottom of the screen.
        self._world_height: int = SCREEN_HEIGHT   # grows as we generate upward

        # ---- Score / high score ----
        self.score:      int = 0
        self.high_score: int = self._load_high_score()
        self._score_start_y: int | None = None
        self._best_score_y:  int | None = None
        self._height_gained: int = 0   # pixels climbed from starting position

        # ---- State ----
        self.game_over: bool = False
        self.events:    list = []

        # ---- Moonquake (Level 2 also has quakes) ----
        self._quake_timer = MOONQUAKE_INTERVAL
        self._snd_quake   = _load_sound(SFX_MOONQUAKE)

        # ---- Comets ----
        self.comets: list[Comet]  = []
        self._comet_timer: int    = COMET_SPAWN_INTERVAL
        self._comet_interval: int = COMET_SPAWN_INTERVAL  # shrinks as player climbs

        # ---- Platforms ----
        self.platforms: list[Platform] = []
        self._highest_platform_y: int  = SCREEN_HEIGHT   # world y of topmost platform
        self._prev_zone: int = 1
        self._static_streak: int = 0

        # ---- Background ----
        self._bg = _load_image(BG_LEVEL2, (SCREEN_WIDTH, SCREEN_HEIGHT))

        # ---- Starting platform ----
        # Full-width starting platform so both players always land on it
        self._start_platform_y = SCREEN_HEIGHT - 100
        start_plat = Platform(
            0,
            self._start_platform_y,
            PLATFORM_STATIC,
            width=SCREEN_WIDTH,
        )
        self.platforms.append(start_plat)
        self._highest_platform_y = SCREEN_HEIGHT - 100

        # ---- Generate initial set of platforms ----
        self._generate_platforms()

        # ---- Music ----
        _start_music(MUSIC_LEVEL2)

    # ------------------------------------------------------------------
    # Procedural generation
    # ------------------------------------------------------------------

    def _generate_platforms(self) -> None:
        """
        Append new platforms above the current highest platform until
        the generation lookahead is satisfied.

        University report — constrained random placement:
          Each new platform is placed:
            • Horizontally: randomly within one of three horizontal zones
              (left / centre / right), cycling to ensure the path is always
              reachable.
            • Vertically: close to Level 1's platform spacing, so the jump
              arcs in config.py are always sufficient to reach the next tile.
          Hidden platform chance is applied independently per platform.
          A minimum of 4 consecutive static platforms is enforced before a
          crumbling platform appears (ensuring a safe recovery path always
          exists).
        """
        zones = [
            (30, SCREEN_WIDTH // 3 - PLATFORM_WIDTH),
            (SCREEN_WIDTH // 3, 2 * SCREEN_WIDTH // 3 - PLATFORM_WIDTH),
            (2 * SCREEN_WIDTH // 3, SCREEN_WIDTH - PLATFORM_WIDTH - 30),
        ]
        target_y = self._highest_platform_y - self.GEN_LOOKAHEAD

        while self._highest_platform_y > target_y:
            # Vertical placement
            gap = random.randint(70, 92)
            world_y = self._highest_platform_y - gap

            # Horizontal placement — move at most ONE zone per step (clamped,
            # never wrapping) so the next platform is always within a single
            # jump of the previous one.
            self._prev_zone = max(0, min(2, self._prev_zone + random.choice([-1, 0, 1])))
            x_min, x_max = zones[self._prev_zone]
            x = random.randint(x_min, max(x_min, x_max))

            # Platform type — enforce safe streak before a crumbling platform
            if self._static_streak >= 4 and random.random() < 0.18:
                kind = PLATFORM_MOVING
                self._static_streak += 1
            elif self._static_streak >= 5 and random.random() < 0.25:
                kind = PLATFORM_CRUMBLE
                self._static_streak = 0
            else:
                kind = PLATFORM_STATIC
                self._static_streak += 1

            # Hidden flag — only static platforms can be hidden, and never two
            # hidden platforms in a row (that would leave an uncrossable gap for
            # a team without Nova).  Nova's spark trail still has plenty of
            # hidden tiles to uncover.
            prev_hidden = self.platforms[-1].hidden if self.platforms else False
            hidden = (
                kind == PLATFORM_STATIC
                and not prev_hidden
                and random.random() < L2_HIDDEN_PLATFORM_CHANCE
            )

            width = PLATFORM_WIDTH

            self.platforms.append(Platform(
                x,
                world_y,
                kind,
                width=width,
                hidden=hidden,
                move_axis=random.choice(["horizontal", "vertical"]),
                move_range=random.randint(45, 75),
                move_speed=random.uniform(0.75, 1.15),
            ))
            self._highest_platform_y = world_y

    # ------------------------------------------------------------------
    # High-score persistence
    # ------------------------------------------------------------------

    def _load_high_score(self) -> int:
        """Read the high score from a plain-text file. Returns 0 if absent."""
        path = os.path.join(os.path.dirname(__file__), "high_score.txt")
        try:
            with open(path, "r") as f:
                return int(f.read().strip())
        except (FileNotFoundError, ValueError):
            return 0

    def _save_high_score(self) -> None:
        """Persist the current high score to disk."""
        path = os.path.join(os.path.dirname(__file__), "high_score.txt")
        try:
            with open(path, "w") as f:
                f.write(str(self.high_score))
        except OSError:
            pass   # if saving fails the game still runs; score is just not persisted

    # ------------------------------------------------------------------
    # Main loop methods
    # ------------------------------------------------------------------

    def update(self, players: list, keys) -> None:
        """
        Advance the Level 2 simulation by one frame.

        Order of operations:
          1. Compute height gained; update score.
          2. Scroll to follow the highest alive player.
          3. Generate new platforms ahead.
          4. Update platform crumble timers; remove broken/off-screen ones.
          5. Update hidden-platform reveal (Nova's spark trail).
          6. Spawn and update comets; scale spawn rate with height.
          7. Moonquake check.
          8. Game-over check (both players dead).
          9. Update particle effects.
        """
        self.events.clear()

        if self.game_over:
            return

        # ---- 1. Height & score ----
        # Initialise scoring to the highest alive player on the first frame.
        # We cannot do this in __init__ because players are not yet created then.
        alive_players = [p for p in players if p.alive]
        if alive_players:
            highest_y = int(min(p.y for p in alive_players))
            if self._score_start_y is None:
                self._score_start_y = highest_y
                self._best_score_y = highest_y

            # In Pygame coords, lower world_y = higher up in the world.
            # Score from the total best height reached so sub-pixel/frame
            # movement cannot be lost to integer truncation.
            self._best_score_y = min(self._best_score_y, highest_y)
            self._height_gained = max(0, self._score_start_y - self._best_score_y)
            self.score = self._height_gained * L2_SCORE_PER_PLATFORM // 100
            if self.score > self.high_score:
                self.high_score = self.score
                self._save_high_score()

        # ---- 2. Scroll ----
        # Follow the player who is highest on screen (smallest screen y)
        # with a smooth lerp so the camera doesn't snap violently.
        target_scroll = self.scroll_y
        for player in players:
            if player.alive:
                # Desired scroll: keep player in the upper third of the screen
                # Correct formula: desired scroll_y so that player appears
                # at SCREEN_HEIGHT//3 from the top.
                # screen_y = world_y - scroll_y => scroll_y = world_y - screen_y
                desired = player.y - SCREEN_HEIGHT // 3
                target_scroll = min(target_scroll, desired)

        # Lerp scroll toward target (smooth camera)
        self.scroll_y = int(self.scroll_y + (target_scroll - self.scroll_y) * 0.08)

        # ---- 3. Generate platforms ----
        if self._highest_platform_y > self.scroll_y - self.GEN_LOOKAHEAD:
            self._generate_platforms()

        # ---- 4. Platforms ----
        for plat in self.platforms:
            plat.update(self.particles)
        _carry_players_on_moving_platforms(players, self.platforms)

        # Remove broken or far-below-screen platforms (memory management)
        cull_threshold = self.scroll_y + SCREEN_HEIGHT + 300
        self.platforms = [
            p for p in self.platforms
            if not p.broken and p.rect.y < cull_threshold
        ]

        # Orion freeze propagation
        for player in players:
            if hasattr(player, "freeze_active") and player.freeze_active:
                player.freeze_nearby(self.platforms)

        # ---- 5. Nova hidden-platform reveal ----
        # For each Nova player, check her spark trail against hidden platforms.
        # A platform within the trail's bounding rect is revealed temporarily.
        for player in players:
            if not hasattr(player, "get_reveal_rect"):
                continue
            reveal_rect = player.get_reveal_rect()
            if reveal_rect is None:
                continue
            for plat in self.platforms:
                if not plat.hidden:
                    continue
                # Both reveal_rect and plat.rect are in world space,
                # so compare directly without any scroll conversion.
                if reveal_rect.colliderect(plat.rect):
                    # Reveal for the spark-trail duration defined in config
                    from config import NOVA_SPARK_DURATION
                    plat.reveal(NOVA_SPARK_DURATION)

        # ---- 6. Comets ----
        # Scale spawn rate: every L2_COMET_RAMP_HEIGHT pixels, reduce interval
        ramp_steps = max(0, self._height_gained // L2_COMET_RAMP_HEIGHT)
        self._comet_interval = max(
            COMET_INTERVAL_L2_MIN,
            COMET_SPAWN_INTERVAL - ramp_steps * L2_COMET_RAMP_STEP,
        )

        self._comet_timer -= 1
        if self._comet_timer <= 0:
            self.comets.append(Comet(self.scroll_y))
            self._comet_timer = self._comet_interval + random.randint(-20, 20)

        for comet in self.comets:
            comet.update(self.platforms, players, self.particles, self.scroll_y)
        self.comets = [c for c in self.comets if c.active]

        # ---- 7. Moonquake ----
        self._quake_timer -= 1
        if self._quake_timer <= 0:
            self._trigger_moonquake()

        # ---- 8. Game-over check ----
        alive_count = sum(1 for p in players if p.alive)
        if alive_count == 0:
            self.game_over = True
            self._save_high_score()
            self.events.append("GAME_OVER")

        # ---- 9. Effects ----
        self.particles.update()

        # Player falls off bottom of screen → damage + safe on-screen respawn
        for player in players:
            if player.alive and player.y > self.scroll_y + SCREEN_HEIGHT + 60:
                player.take_damage()
                if player.alive:
                    _respawn_on_screen(player, self.platforms, self.scroll_y)

    def _trigger_moonquake(self) -> None:
        """
        Moonquake event — same behaviour as Level 1 but also resets the
        scroll position slightly downward to increase challenge.

        University report:
          The downward scroll nudge (adding to scroll_y) briefly exposes
          lower world-y values, meaning the bottom of the screen drops —
          increasing the risk of players falling off.  This is a difficulty
          spike that rewards players who have built a comfortable height buffer.
        """
        _play(self._snd_quake)
        self.screen_effect.shake(MOONQUAKE_SHAKE_MAGNITUDE, MOONQUAKE_SHAKE_DURATION)
        self.screen_effect.flash(PURPLE, 20)

        for plat in self.platforms:
            shift = random.randint(-QUAKE_SHIFT_RANGE, QUAKE_SHIFT_RANGE)
            plat.shift_horizontal(shift)

        self._quake_timer = MOONQUAKE_INTERVAL
        self.events.append("MOONQUAKE")

    # ------------------------------------------------------------------
    # Draw
    # ------------------------------------------------------------------

    def draw(self, surface: pygame.Surface) -> None:
        """
        Render Level 2 from back to front:
          1. Background (tiled vertically for parallax feel)
          2. Platforms (hidden ones only drawn if revealed)
          3. Comets
          4. Particles
          5. Screen flash
        """
        # ---- 1. Background ----
        bg_h  = self._bg.get_height()
        start = -(self.scroll_y % bg_h)
        y     = start
        while y < SCREEN_HEIGHT:
            surface.blit(self._bg, (0, y))
            y += bg_h

        # ---- 2. Platforms ----
        for plat in self.platforms:
            plat.draw(surface, self.scroll_y)

        # ---- 3. Comets ----
        for comet in self.comets:
            comet.draw(surface, self.scroll_y)

        # ---- 4. Particles ----
        self.particles.draw(surface)

        # ---- 5. Flash ----
        self.screen_effect.draw_flash(surface)

    def _draw_score(self, surface: pygame.Surface) -> None:
        """
        Render the current score and high score in the top-right corner.

        University report:
          Using pygame.font.SysFont('monospace', ...) ensures a consistent
          look across platforms without requiring a bundled font file.
          The shadow (drawn 2 px offset in black) improves legibility against
          the starfield background without needing a HUD panel.
        """
        try:
            font_lg = pygame.font.SysFont("monospace", 22, bold=True)
            font_sm = pygame.font.SysFont("monospace", 16)
        except Exception:
            return   # font unavailable — skip draw silently

        # Score
        score_surf   = font_lg.render(f"SCORE  {self.score:>7}", True, GOLD)
        score_shadow = font_lg.render(f"SCORE  {self.score:>7}", True, BLACK)
        surface.blit(score_shadow, (SCREEN_WIDTH - 202, 12))
        surface.blit(score_surf,   (SCREEN_WIDTH - 204, 10))

        # High score
        hi_surf   = font_sm.render(f"BEST   {self.high_score:>7}", True, CYAN)
        hi_shadow = font_sm.render(f"BEST   {self.high_score:>7}", True, BLACK)
        surface.blit(hi_shadow, (SCREEN_WIDTH - 202, 36))
        surface.blit(hi_surf,   (SCREEN_WIDTH - 204, 34))

        # Height gained
        ht_surf = font_sm.render(f"HEIGHT {self._height_gained:>5}m", True, WHITE)
        surface.blit(ht_surf, (SCREEN_WIDTH - 204, 56))

    def get_events(self) -> list:
        """Return and clear the event queue for this frame."""
        evts = self.events[:]
        self.events.clear()
        return evts
