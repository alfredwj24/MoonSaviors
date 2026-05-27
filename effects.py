"""
effects.py — Moon Saviors
=========================
Handles ALL visual special effects in the game.

Effect systems implemented here:
  • ParticleSystem  — comet explosions, landing dust, crystal-grab aura
  • ScreenEffect    — screen shake, full-screen colour flash, freeze tint
  • SparkTrail      — Nova's movement trail that reveals hidden platforms
  • ShieldBubble    — Luna's pulsing protective bubble
  • GlowEffect      — pulsing halo around moon-crystal pickups

University report note:
  Every effect is built on one of two Pygame primitives:
    1. pygame.Surface   — for blitting images and alpha-blended overlays
    2. pygame.draw.*    — for procedurally generated geometry (circles, rects)
  Particle systems update a list of small data-dictionaries each frame;
  no heavy physics engine is needed because the interactions are purely
  visual and never affect game-play collision.
"""

import math
import random
import pygame

from config import (
    # Colours
    WHITE, BLACK, CYAN, CYAN_DARK, GREEN, PINK, GOLD, PURPLE, TRANSPARENT,
    COLOR_SHIELD, COLOR_FREEZE, COLOR_SPARK, COLOR_COMET_EXP, COLOR_CRYSTAL,
    # Asset paths
    FX_COMET_EXPLOSION, FX_SPARK_TRAIL, FX_SHIELD_BUBBLE, FX_MOON_CRYSTAL,
    # Screen dimensions
    SCREEN_WIDTH, SCREEN_HEIGHT,
    # Timing constants
    FPS,
    # Crystal effect sizes
    CRYSTAL_FLASH_FRAMES, CRYSTAL_AURA_RADIUS,
    # Nova spark duration
    NOVA_SPARK_DURATION,
)


# ---------------------------------------------------------------------------
# ASSET LOADER HELPER
# ---------------------------------------------------------------------------

def _load_image(path: str, size: tuple | None = None) -> pygame.Surface:
    """
    Attempt to load an image from *path*.

    If the file is missing or corrupt, a bright-magenta fallback surface is
    returned instead.  This prevents a FileNotFoundError from crashing the
    game at runtime — the assignment requires graceful degradation.

    Parameters
    ----------
    path : str
        Absolute path produced by config.asset().
    size : tuple (w, h) or None
        If provided the image is scaled to this size after loading.

    Returns
    -------
    pygame.Surface
        Either the loaded/scaled asset or a coloured fallback rectangle.
    """
    try:
        img = pygame.image.load(path).convert_alpha()
        if size:
            img = pygame.transform.smoothscale(img, size)
        return img
    except (FileNotFoundError, pygame.error):
        # Fallback: a bright-magenta rectangle so missing assets are obvious
        surf = pygame.Surface(size if size else (32, 32), pygame.SRCALPHA)
        surf.fill((255, 0, 255, 200))
        return surf


# ---------------------------------------------------------------------------
# PARTICLE SYSTEM
# ---------------------------------------------------------------------------

class ParticleSystem:
    """
    General-purpose 2-D particle system.

    A 'particle' is a lightweight dictionary that stores all mutable state for
    a single spark/dust/aura dot.  Each frame, ParticleSystem.update() applies
    simple kinematic equations to every particle and removes expired ones.
    Keeping data in plain dicts (rather than class instances) minimises
    per-object Python overhead in tight loops.

    Supported emitter types
    -----------------------
    comet_impact(pos)   — outward burst using the comet-explosion sprite
    landing_dust(pos)   — small grey puffs emitted when a player lands
    crystal_aura(pos)   — continuous green glowing sparks for the win event
    """

    def __init__(self):
        # Master list; each element is a dict describing one live particle
        self.particles: list[dict] = []

        # Pre-load the comet-explosion sprite sheet fragment used as a
        # texture stamp for each explosion particle
        self._explosion_img = _load_image(FX_COMET_EXPLOSION, (64, 64))

    # ------------------------------------------------------------------
    # Public emitter methods
    # ------------------------------------------------------------------

    def comet_impact(self, pos: tuple[int, int]) -> None:
        """
        Spawn a burst of outward-flying particles at *pos*.

        University report — technique:
          Each particle is given a random angle (0–360°) and a random speed.
          The velocity components are derived from sin/cos so particles spread
          evenly in all directions.  An alpha value starts at 255 (fully
          opaque) and decreases each frame, creating a natural fade-out.
          A 'scale' field shrinks the particle over its lifetime so distant
          sparks appear to vanish into space.
        """
        num_particles = random.randint(24, 36)  # more particles = bigger boom
        for _ in range(num_particles):
            angle_deg = random.uniform(0, 360)
            angle_rad = math.radians(angle_deg)
            speed     = random.uniform(2.5, 7.0)

            self.particles.append({
                "type"    : "comet",
                "x"       : float(pos[0]),
                "y"       : float(pos[1]),
                "vx"      : math.cos(angle_rad) * speed,
                "vy"      : math.sin(angle_rad) * speed,
                "alpha"   : 255,
                "fade"    : random.randint(6, 12),   # alpha lost per frame
                "scale"   : random.uniform(0.6, 1.2),
                "shrink"  : random.uniform(0.015, 0.03),  # scale lost per frame
                "color"   : random.choice([PINK, GOLD, WHITE, (255, 140, 0)]),
                "size"    : random.randint(4, 10),    # radius for circle fallback
                "lifetime": random.randint(20, 45),
                "age"     : 0,
            })

    def landing_dust(self, pos: tuple[int, int]) -> None:
        """
        Emit a small cloud of grey dust puffs when a player lands on a platform.

        University report — technique:
          Particles are given a mostly-upward velocity (negative vy) with a
          small horizontal spread, mimicking fine moon-dust kicked up on impact.
          They decelerate horizontally via a 'drag' multiplier applied each frame.
        """
        for _ in range(random.randint(6, 10)):
            self.particles.append({
                "type"    : "dust",
                "x"       : float(pos[0] + random.randint(-20, 20)),
                "y"       : float(pos[1]),
                "vx"      : random.uniform(-1.5, 1.5),
                "vy"      : random.uniform(-2.5, -0.8),
                "alpha"   : 200,
                "fade"    : random.randint(8, 14),
                "color"   : random.choice([(180, 180, 200), (160, 160, 180), (200, 195, 210)]),
                "size"    : random.randint(3, 7),
                "drag"    : 0.88,    # horizontal velocity is multiplied by this each frame
                "lifetime": random.randint(15, 30),
                "age"     : 0,
            })

    def crystal_aura(self, pos: tuple[int, int]) -> None:
        """
        Continuously emit upward-floating green sparks for the crystal-grab
        victory event.  Call this every frame while the win animation plays.

        University report — technique:
          A small number of particles (2–4 per frame) rise upward with a sine-
          wave horizontal wobble applied inside update(), giving an organic
          'magical' floating motion rather than a straight line.
        """
        for _ in range(random.randint(2, 4)):
            self.particles.append({
                "type"    : "aura",
                "x"       : float(pos[0] + random.randint(-CRYSTAL_AURA_RADIUS,
                                                           CRYSTAL_AURA_RADIUS)),
                "y"       : float(pos[1] + random.randint(-20, 20)),
                "vx"      : random.uniform(-0.5, 0.5),
                "vy"      : random.uniform(-1.5, -0.5),   # rises upward
                "alpha"   : random.randint(180, 255),
                "fade"    : random.randint(4, 8),
                "color"   : random.choice([GREEN, (100, 255, 150), COLOR_CRYSTAL, WHITE]),
                "size"    : random.randint(3, 8),
                "wobble"  : random.uniform(0.05, 0.15),   # amplitude of horizontal sine
                "age"     : 0,
                "lifetime": random.randint(30, 60),
            })

    # ------------------------------------------------------------------
    # Update & Draw
    # ------------------------------------------------------------------

    def update(self) -> None:
        """
        Advance every live particle by one frame.

        Steps applied each frame:
          1. Increment age; remove particle if lifetime exceeded.
          2. Move particle by its velocity vector.
          3. Apply drag (dust only).
          4. Apply sine-wave wobble (aura only).
          5. Reduce alpha; clamp to [0, 255].
          6. Shrink scale (comet sparks only).
        """
        alive = []
        for p in self.particles:
            p["age"] += 1
            if p["age"] >= p["lifetime"] or p["alpha"] <= 0:
                continue  # particle has expired — drop it

            # --- Kinematics ---
            p["x"] += p["vx"]
            p["y"] += p["vy"]

            # Horizontal drag for dust particles
            if p["type"] == "dust":
                p["vx"] *= p["drag"]

            # Sine-wave horizontal wobble for aura particles
            if p["type"] == "aura":
                p["x"] += math.sin(p["age"] * p["wobble"] * math.pi) * 0.8

            # --- Fade ---
            p["alpha"] = max(0, p["alpha"] - p["fade"])

            # --- Shrink (comet sparks) ---
            if p["type"] == "comet":
                p["scale"] = max(0.05, p["scale"] - p["shrink"])

            alive.append(p)

        self.particles = alive

    def draw(self, surface: pygame.Surface) -> None:
        """
        Render every live particle onto *surface*.

        University report — rendering technique:
          Rather than blitting the full explosion image for every particle
          (which would be expensive at 30+ particles), we use pygame.draw.circle
          for small sparks and only use the image stamp for the largest comet
          particles (scale > 0.8).  Alpha blending is achieved by creating a
          temporary Surface with per-pixel alpha (SRCALPHA), drawing onto it,
          and blitting it with the particle's current alpha value.
        """
        for p in self.particles:
            alpha = int(p["alpha"])
            color = p["color"]
            size  = max(1, int(p["size"]))

            if p["type"] == "comet" and p["scale"] > 0.5:
                # --- Image-stamp path for comet explosion particles ---
                # Scale the explosion sprite according to current particle scale
                img_size = max(4, int(40 * p["scale"]))
                stamp = pygame.transform.smoothscale(
                    self._explosion_img, (img_size, img_size)
                )
                stamp.set_alpha(alpha)
                # Centre the stamp on the particle position
                blit_x = int(p["x"]) - img_size // 2
                blit_y = int(p["y"]) - img_size // 2
                surface.blit(stamp, (blit_x, blit_y))
            else:
                # --- Circle path for dust and aura particles ---
                # Create a small transparent surface, draw a filled circle,
                # set its overall alpha, then blit to the main surface.
                # Using SRCALPHA allows smooth fade even over complex backgrounds.
                diameter = size * 2
                tmp = pygame.Surface((diameter, diameter), pygame.SRCALPHA)
                pygame.draw.circle(tmp, (*color, alpha), (size, size), size)
                surface.blit(tmp, (int(p["x"]) - size, int(p["y"]) - size))


# ---------------------------------------------------------------------------
# SCREEN EFFECT
# ---------------------------------------------------------------------------

class ScreenEffect:
    """
    Manages full-screen transient effects that modify how the entire game view
    is presented, without touching individual game objects.

    Three independent sub-systems run in parallel:
      • Shake   — randomly offsets the blit position of the game surface
      • Flash   — overlays a coloured rectangle that fades out
      • Tint    — applies a semi-transparent colour overlay to a subsurface
    """

    def __init__(self):
        # --- Shake state ---
        self._shake_intensity: float = 0   # maximum pixel offset
        self._shake_frames: int      = 0   # frames remaining
        self._shake_duration: int    = 1   # total frames of the current shake (for damping)
        self.offset: tuple[int, int] = (0, 0)  # current (dx, dy) applied by main.py

        # --- Flash state ---
        self._flash_color:    tuple  = WHITE
        self._flash_alpha:    int    = 0
        self._flash_frames:   int    = 0
        self._flash_duration: int    = 1   # avoid division by zero

        # Reusable full-screen surface for the flash overlay
        self._flash_surf = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)

    # ------------------------------------------------------------------
    # Public trigger methods
    # ------------------------------------------------------------------

    def shake(self, intensity: float, duration: int) -> None:
        """
        Begin a screen-shake effect.

        Parameters
        ----------
        intensity : float
            Maximum pixel displacement per frame (e.g. 12 for a moonquake).
        duration : int
            Number of frames the shake lasts.

        University report — technique:
          Each frame, a random dx and dy in the range [-intensity, +intensity]
          are stored in self.offset.  main.py reads this offset when blitting
          the game surface, shifting the entire rendered world by that amount.
          The intensity is linearly damped — it decreases proportionally as
          the remaining frame count falls — so the shake starts violent and
          smoothly settles back to zero.
        """
        self._shake_intensity = intensity
        self._shake_frames    = duration
        self._shake_duration  = max(1, duration)

    def flash(self, color: tuple, duration: int) -> None:
        """
        Trigger a full-screen colour flash that fades to transparent.

        Parameters
        ----------
        color    : RGB tuple   e.g. WHITE for the crystal-grab win event.
        duration : int         Frames until the flash is fully transparent.

        University report — technique:
          An SRCALPHA pygame.Surface the size of the screen is filled with
          *color* at alpha = 255 when the flash is triggered.  Each frame,
          alpha is decremented proportionally so it reaches 0 exactly at
          *duration* frames.  This surface is blitted on top of everything
          else in main.py's draw loop, creating the impression that the whole
          world lights up.
        """
        self._flash_color    = color
        self._flash_alpha    = 255
        self._flash_frames   = duration
        self._flash_duration = max(1, duration)

    def freeze_tint(self, surface: pygame.Surface,
                    rect: pygame.Rect,
                    strength: int = 90) -> None:
        """
        Paint a blue/cyan tint over the rectangle *rect* on *surface*.

        Used to visually indicate that Orion's freeze ability is active on a
        particular platform.

        Parameters
        ----------
        surface  : pygame.Surface  The target surface (the game screen).
        rect     : pygame.Rect     The region to tint (platform bounding box).
        strength : int             Alpha of the tint overlay (0–255).

        University report — technique:
          A temporary Surface is created at the size of *rect* with SRCALPHA.
          It is filled with the freeze colour at *strength* alpha and blitted
          directly onto *surface* at rect.topleft.  Because the temp surface
          has SRCALPHA, the tint blends with whatever is already drawn beneath
          it — the platform texture shows through while gaining an icy hue.
        """
        tint = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        tint.fill((*COLOR_FREEZE, strength))
        surface.blit(tint, rect.topleft)

    # ------------------------------------------------------------------
    # Update & Draw
    # ------------------------------------------------------------------

    def update(self) -> None:
        """
        Advance the shake and flash timers by one frame.

        Shake:  If active, compute a new random offset whose maximum magnitude
                is proportionally damped based on remaining frames.
        Flash:  If active, decrement alpha linearly so it reaches 0 at the
                end of the flash duration.
        """
        # --- Shake ---
        if self._shake_frames > 0:
            # Linear damping: shake is strongest at the start and eases to zero
            # as the remaining frames run out (frames_left / total_duration).
            proportion = self._shake_frames / self._shake_duration
            mag = self._shake_intensity * proportion
            dx  = random.uniform(-mag, mag)
            dy  = random.uniform(-mag, mag)
            self.offset = (int(dx), int(dy))
            self._shake_frames -= 1
        else:
            self.offset = (0, 0)

        # --- Flash ---
        if self._flash_frames > 0:
            # Decrease alpha so that after _flash_duration frames it equals 0
            decay = 255 / self._flash_duration
            self._flash_alpha = max(0, self._flash_alpha - decay)
            self._flash_frames -= 1

    def draw_flash(self, surface: pygame.Surface) -> None:
        """
        Blit the current flash overlay onto *surface*.

        This should be called LAST in the draw loop so the flash appears
        above all game objects (characters, platforms, HUD etc.).
        """
        if self._flash_alpha > 0:
            self._flash_surf.fill((*self._flash_color, int(self._flash_alpha)))
            surface.blit(self._flash_surf, (0, 0))


# ---------------------------------------------------------------------------
# SPARK TRAIL
# ---------------------------------------------------------------------------

class SparkTrail:
    """
    Renders a glowing golden trail behind Nova as she moves.

    Each call to emit() adds a new 'stamp' — a scaled copy of the spark-trail
    asset positioned at Nova's current location.  Stamps fade out over
    NOVA_SPARK_DURATION / 2 frames, giving a short persistence-of-vision tail.

    Level 2 hidden-platform reveal
    --------------------------------
    In Level 2 some platforms are flagged as hidden=True and are normally
    invisible.  SparkTrail.get_reveal_rect() returns a pygame.Rect covering
    the trail's current bounding box.  The level renderer compares each hidden
    platform's rect against this reveal rect; those that intersect are drawn
    for NOVA_SPARK_DURATION frames.
    """

    # How long (frames) a single stamp stays visible
    STAMP_LIFETIME = FPS // 2   # 30 frames = 0.5 seconds

    def __init__(self):
        self._stamps: list[dict] = []   # list of active trail stamps
        self._spark_img = _load_image(FX_SPARK_TRAIL, (40, 20))

        # Rect that encloses all currently visible stamps (used for platform reveal)
        self._reveal_rect: pygame.Rect | None = None

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def emit(self, pos: tuple[int, int]) -> None:
        """
        Drop a new spark stamp at *pos* (Nova's centre position).

        University report — technique:
          Rather than redrawing a continuous line, we store discrete 'stamps'.
          Each stamp records its initial position and birth frame so that its
          current alpha can be computed from age alone:
              alpha = 255 * (1 - age / STAMP_LIFETIME)
          This gives a smooth linear fade-out without storing an alpha field
          that drifts due to floating-point rounding across many frames.
        """
        self._stamps.append({
            "x"   : pos[0],
            "y"   : pos[1],
            "age" : 0,
        })

    def update(self) -> None:
        """
        Age every stamp and remove expired ones.
        Also recompute the bounding rect used for platform reveal.
        """
        alive = []
        min_x, min_y = SCREEN_WIDTH, SCREEN_HEIGHT
        max_x, max_y = 0, 0

        for s in self._stamps:
            s["age"] += 1
            if s["age"] < self.STAMP_LIFETIME:
                alive.append(s)
                # Track bounding box for the reveal rect
                min_x = min(min_x, s["x"] - 40)
                min_y = min(min_y, s["y"] - 20)
                max_x = max(max_x, s["x"] + 40)
                max_y = max(max_y, s["y"] + 20)

        self._stamps = alive

        if alive:
            self._reveal_rect = pygame.Rect(
                min_x, min_y,
                max_x - min_x,
                max_y - min_y,
            )
        else:
            self._reveal_rect = None

    def draw(self, surface: pygame.Surface, scroll_y: int = 0) -> None:
        """
        Blit every stamp onto *surface* at its current alpha.

        Parameters
        ----------
        scroll_y : int
            World-to-screen Y offset.  Stamps are stored in world coordinates
            (emitted at player.center which is world space) so we subtract
            scroll_y here to convert each stamp to screen space before blitting.

        University report — rendering technique:
          set_alpha() applies a uniform transparency to the whole surface.
          Because we create a fresh copy of the image each frame with
          pygame.transform.scale(), the alpha is applied to a clean surface
          and the original self._spark_img is never mutated.  This is
          important for correctness when multiple stamps are drawn in the
          same frame at different alpha levels.
        """
        for s in self._stamps:
            # Compute alpha from age: starts at 255, ends at 0
            progress = s["age"] / self.STAMP_LIFETIME      # 0.0 → 1.0
            alpha    = int(255 * (1.0 - progress))

            # Scale stamp slightly bigger when fresh, smaller when old —
            # creates a subtle "firework" expand-then-shrink feel
            scale_factor = 1.0 + 0.3 * (1.0 - progress)
            w = int(40 * scale_factor)
            h = int(20 * scale_factor)

            stamp = pygame.transform.smoothscale(self._spark_img, (w, h))
            stamp.set_alpha(alpha)

            # Convert world position to screen position by subtracting scroll_y
            screen_x = s["x"] - w // 2
            screen_y = s["y"] - scroll_y - h // 2
            surface.blit(stamp, (screen_x, screen_y))

    def get_reveal_rect(self) -> pygame.Rect | None:
        """
        Return a Rect covering all live trail stamps, or None if trail is empty.

        The level renderer uses this rect to decide which hidden platforms
        (in Level 2) should become temporarily visible.
        """
        return self._reveal_rect

    def clear(self) -> None:
        """Remove all active stamps (e.g. when Nova uses her ability again)."""
        self._stamps.clear()
        self._reveal_rect = None


# ---------------------------------------------------------------------------
# SHIELD BUBBLE
# ---------------------------------------------------------------------------

class ShieldBubble:
    """
    Luna's protective shield — a pulsing bubble that blocks one comet hit.

    University report — technique:
      The bubble is rendered by scaling the shield sprite up and down each
      frame using a sine wave:
          scale = BASE_SCALE + PULSE_AMP * sin(2π * age / PULSE_PERIOD)
      This creates a smooth 'breathing' animation with no additional state
      beyond a frame counter.  When a comet collision is detected, the game
      calls absorb(); the bubble plays a brief 'burst' animation (rapid alpha
      fade) and then deactivates.
    """

    BASE_SCALE  = 1.0    # nominal scale factor (1 = original size)
    PULSE_AMP   = 0.08   # amplitude of the breathing pulse (±8 % size)
    PULSE_PERIOD = 90    # frames for one full pulse cycle (1.5 s at 60 FPS)

    def __init__(self):
        self.active: bool = False   # True while the shield is protecting Luna
        self._age: int    = 0       # frame counter for the sine-wave pulse
        self._alpha: int  = 220     # current opacity of the bubble

        # Burst state — plays when the shield absorbs a hit
        self._bursting: bool   = False
        self._burst_age: int   = 0
        self._burst_duration   = 20  # frames for the burst-fade animation

        # Load the shield image (square, centred on Luna)
        self._img = _load_image(FX_SHIELD_BUBBLE, (96, 96))

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def activate(self) -> None:
        """Enable the shield (called when Luna uses her special ability)."""
        self.active   = True
        self._age     = 0
        self._alpha   = 220
        self._bursting = False

    def absorb(self) -> None:
        """
        Called when a comet hits Luna while the shield is active.

        Triggers the burst animation, then deactivates after BURST_DURATION
        frames.  The game should check ShieldBubble.active each frame;
        once False the comet's damage logic is skipped.
        """
        if not self.active:
            return
        self._bursting   = True
        self._burst_age  = 0

    def update(self) -> None:
        """
        Advance the shield animation by one frame.

        • Normal state: increment _age to drive the sine-wave pulse.
        • Bursting: rapidly fade alpha to 0 and then deactivate.
        """
        if not self.active:
            return

        if self._bursting:
            self._burst_age += 1
            # Rapidly fade out during burst
            self._alpha = max(0, 220 - int(220 * self._burst_age / self._burst_duration))
            if self._burst_age >= self._burst_duration:
                self.active = False   # shield consumed
        else:
            self._age += 1

    def draw(self, surface: pygame.Surface, pos: tuple[int, int]) -> None:
        """
        Render the shield bubble centred on *pos* (Luna's centre).

        Parameters
        ----------
        surface : pygame.Surface  The game screen.
        pos     : tuple (cx, cy)  Centre of Luna's sprite.

        University report — rendering technique:
          The sine-wave pulse is applied via pygame.transform.smoothscale,
          which performs bilinear filtering for a smooth size transition.
          set_alpha() then applies the current transparency.  The combination
          of smoothscale + set_alpha is inexpensive because the shield surface
          is small (≤160×160 px) and only one shield exists at a time.
        """
        if not self.active:
            return

        # Compute current scale from sine wave (or skip if bursting)
        if self._bursting:
            scale = self.BASE_SCALE + 0.2   # bubble 'pops' slightly outward
        else:
            sine_val = math.sin(2 * math.pi * self._age / self.PULSE_PERIOD)
            scale    = self.BASE_SCALE + self.PULSE_AMP * sine_val

        # Scale the sprite
        base_size = 96
        new_size  = max(4, int(base_size * scale))
        scaled    = pygame.transform.smoothscale(self._img, (new_size, new_size))
        scaled.set_alpha(self._alpha)

        # Blit centred on Luna
        blit_x = pos[0] - new_size // 2
        blit_y = pos[1] - new_size // 2
        surface.blit(scaled, (blit_x, blit_y))


# ---------------------------------------------------------------------------
# GLOW EFFECT
# ---------------------------------------------------------------------------

class GlowEffect:
    """
    Renders a pulsing coloured halo around the moon-crystal pickup.

    University report — technique:
      The halo is drawn as a series of concentric circles with decreasing
      alpha values — an additive-blend approximation that is efficient in
      Pygame's default surface mode.  The outer radius oscillates using a
      sine wave, making the glow appear to 'breathe'.

      For the moon-crystal icon itself, pygame.image.load is used with an
      SRCALPHA surface so the transparent background of the PNG does not
      appear as a white box over the platform.
    """

    # Glow parameters
    GLOW_COLOR     = COLOR_CRYSTAL     # base halo colour
    GLOW_LAYERS    = 5                 # number of concentric rings
    BASE_RADIUS    = 28                # inner halo radius (px)
    MAX_RADIUS     = 48                # outer halo radius (px)
    PULSE_PERIOD   = 80                # frames for one full opacity cycle
    BASE_ALPHA     = 80                # starting opacity of the outermost ring
    ICON_SIZE      = (36, 36)          # displayed size of the crystal icon

    def __init__(self):
        self._age: int = 0
        self._crystal_img = _load_image(FX_MOON_CRYSTAL, self.ICON_SIZE)

    def update(self) -> None:
        """Advance the animation clock by one frame."""
        self._age += 1

    def draw(self, surface: pygame.Surface, pos: tuple[int, int]) -> None:
        """
        Render the pulsing halo and crystal icon centred on *pos*.

        Parameters
        ----------
        surface : pygame.Surface  The game screen.
        pos     : tuple (cx, cy)  The crystal's centre position in screen space.

        University report — layered-circle technique:
          GLOW_LAYERS concentric circles are drawn from outermost to innermost.
          The outermost ring has alpha = BASE_ALPHA; each successive ring is
          slightly more opaque, so the glow is brighter at the core.
          A temporary SRCALPHA surface is used for each ring so the circles
          blend with the background rather than painting a solid colour.
          The radius of the outermost ring oscillates with a sine wave:
              r = BASE_RADIUS + (MAX_RADIUS - BASE_RADIUS) * 0.5 * (1 + sin(ω*t))
          This keeps the radius within [BASE_RADIUS, MAX_RADIUS] at all times.
        """
        # Compute the current outer radius from the sine wave
        phase = 2 * math.pi * self._age / self.PULSE_PERIOD
        t     = 0.5 * (1 + math.sin(phase))   # oscillates between 0.0 and 1.0
        outer_r = int(self.BASE_RADIUS + (self.MAX_RADIUS - self.BASE_RADIUS) * t)

        # Draw each halo ring (outermost first so inner rings paint on top)
        for i in range(self.GLOW_LAYERS):
            layer_fraction = i / max(1, self.GLOW_LAYERS - 1)  # 0.0 (outer) → 1.0 (inner)
            radius = max(2, int(outer_r * (1.0 - layer_fraction * 0.5)))
            alpha  = int(self.BASE_ALPHA + layer_fraction * 100)  # inner rings are brighter
            alpha  = min(200, alpha)

            # Temporary surface for this ring (prevents alpha bleed between layers)
            diameter = radius * 2 + 4
            tmp = pygame.Surface((diameter, diameter), pygame.SRCALPHA)
            pygame.draw.circle(
                tmp,
                (*self.GLOW_COLOR, alpha),
                (radius + 2, radius + 2),
                radius,
            )
            surface.blit(tmp, (pos[0] - radius - 2, pos[1] - radius - 2))

        # Draw the crystal icon centred on pos (rendered after the glow so it
        # appears in front of the halo rings)
        icon_w, icon_h = self.ICON_SIZE
        surface.blit(
            self._crystal_img,
            (pos[0] - icon_w // 2, pos[1] - icon_h // 2),
        )
