"""
config.py — Moon Saviors
========================
Central configuration file for the Moon Saviors 2-player vertical platformer.
ALL constants, asset paths, colours, and control bindings live here.
Every other module imports from this file so that tuning values or swapping
assets only ever requires a single edit in one place.
"""

import os
import pygame  # imported only for key constants (K_*); no display calls here

# ---------------------------------------------------------------------------
# PATHS
# ---------------------------------------------------------------------------

# Root of the assets folder, relative to the location of this file.
# Using os.path guarantees the game works regardless of the working directory
# from which `python main.py` is launched.
#
# The asset files may live either inside a dedicated "assets/" subfolder OR
# directly alongside this file (backgrounds/, characters/, platforms/, ...
# at the project root).  We auto-detect which layout is present so the game
# finds its assets in both cases instead of silently falling back to
# placeholder graphics when the "assets/" folder is absent.
_BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
_ASSETS_SUBDIR = os.path.join(_BASE_DIR, "assets")
ASSETS_DIR     = _ASSETS_SUBDIR if os.path.isdir(_ASSETS_SUBDIR) else _BASE_DIR


def asset(relative_path: str) -> str:
    """
    Return the full path to an asset file.

    Parameters
    ----------
    relative_path : str
        Path relative to the assets/ folder, e.g. "backgrounds/Level 1 Background.jpg"

    Returns
    -------
    str
        Absolute path to the asset.  The file may or may not exist — every
        loader must check and fall back gracefully (see fallback helpers in
        each module).
    """
    return os.path.join(ASSETS_DIR, relative_path)


# ---------------------------------------------------------------------------
# ASSET PATHS — Backgrounds
# ---------------------------------------------------------------------------

BG_CHARACTER_SELECT = asset("backgrounds/Character select background.jpg")
BG_LEVEL1          = asset("backgrounds/Level 1 Background.jpg")
BG_LEVEL2          = asset("backgrounds/Level 2 Background.jpg")

# ---------------------------------------------------------------------------
# ASSET PATHS — Characters
# ---------------------------------------------------------------------------

SPRITE_LUNA  = asset("characters/Luna idle.png")
SPRITE_NOVA  = asset("characters/Nova idle.png")
SPRITE_ORION = asset("characters/Orion idle.png")
SPRITE_LUNA_WALK_EAST  = asset("characters/Luna walk east.png")
SPRITE_LUNA_WALK_WEST  = asset("characters/Luna walk west.png")
SPRITE_NOVA_WALK_EAST  = asset("characters/Nova walking east.png")
SPRITE_NOVA_WALK_WEST  = asset("characters/Nova walking west.png")
SPRITE_ORION_WALK_EAST = asset("characters/Orion walk east.png")
SPRITE_ORION_WALK_WEST = asset("characters/Orion walk west.png")
SPRITE_LUNA_JUMP_EAST  = asset("characters/Luna jump east.png")
SPRITE_LUNA_JUMP_WEST  = asset("characters/Luna jump west.png")
SPRITE_NOVA_JUMP_EAST  = asset("characters/Nova jump east.png")
SPRITE_NOVA_JUMP_WEST  = asset("characters/Nova jump west.png")
SPRITE_ORION_JUMP_EAST = asset("characters/Orion jump east.png")
SPRITE_ORION_JUMP_WEST = asset("characters/Orion jump west.png")
SPRITE_LUNA_JUMP_IDLE  = asset("characters/Luna jump.png")
SPRITE_NOVA_JUMP_IDLE  = asset("characters/Nova jump.png")
SPRITE_ORION_JUMP_IDLE = asset("characters/Orion jump.png")

# ---------------------------------------------------------------------------
# ASSET PATHS — Effects
# ---------------------------------------------------------------------------

FX_COMET          = asset("effects/comet.png")
FX_COMET_EXPLOSION = asset("effects/comet explosion.png")
FX_MOON_CRYSTAL   = asset("effects/moon crystal.png")
FX_SHIELD_BUBBLE  = asset("effects/shield bubble.png")
FX_SPARK_TRAIL    = asset("effects/spark trail.png")

# ---------------------------------------------------------------------------
# ASSET PATHS — Platforms & HUD icons
# ---------------------------------------------------------------------------

PLATFORM_STATIC    = asset("platforms/static platform.png")
PLATFORM_CRUMBLING = asset("platforms/crumbling platform.png")
ICON_LIFE_COUNTER  = asset("platforms/life counter icon.png")

# ---------------------------------------------------------------------------
# ASSET PATHS — UI
# ---------------------------------------------------------------------------

ICON_CRYSTAL_HUD = asset("ui/crystal hud icon.png")

# ---------------------------------------------------------------------------
# ASSET PATHS — Music  (streamed, not buffered)
# ---------------------------------------------------------------------------

MUSIC_CHARACTER_SELECT = asset("music/character select music.mp3")
MUSIC_LEVEL1           = asset("music/level 1 music.mp3")
MUSIC_LEVEL2           = asset("music/level 2 music.mp3")

# ---------------------------------------------------------------------------
# ASSET PATHS — Sound Effects  (loaded into memory for low-latency playback)
# ---------------------------------------------------------------------------

SFX_JUMP             = asset("sfx/jump.wav")
SFX_COMET_IMPACT     = asset("sfx/comet_impact.wav")
SFX_CRYSTAL_PICKUP   = asset("sfx/crystal_pickup.wav")
SFX_MOONQUAKE        = asset("sfx/moonquake.wav")
SFX_PLATFORM_CRUMBLE = asset("sfx/platform_crumble.flac")
SFX_PLAYER_FALL      = asset("sfx/player_fall.wav")
SFX_VICTORY          = asset("sfx/victorysound.wav")

# ---------------------------------------------------------------------------
# SCREEN & DISPLAY SETTINGS
# ---------------------------------------------------------------------------

SCREEN_WIDTH  = 800   # px — portrait orientation suits a vertical platformer
SCREEN_HEIGHT = 900   # px
SCREEN_TITLE  = "Moon Saviors"
FPS           = 60    # target frames per second

# ---------------------------------------------------------------------------
# GAME STATES
# Stored as plain strings so log/debug messages are human-readable.
# ---------------------------------------------------------------------------

STATE_MENU             = "MENU"
STATE_CHARACTER_SELECT = "CHARACTER_SELECT"
STATE_LEVEL1           = "LEVEL1"
STATE_LEVEL2           = "LEVEL2"
STATE_GAME_OVER        = "GAME_OVER"
STATE_WIN              = "WIN"

# ---------------------------------------------------------------------------
# PHYSICS & MOVEMENT
# ---------------------------------------------------------------------------

GRAVITY         = 0.55   # px/frame² — lower than Earth to simulate Moon gravity
SCROLL_SPEED    = 2      # px/frame — base upward scroll speed in Level 1
MAX_FALL_SPEED  = 18     # px/frame — terminal velocity cap

# Player horizontal movement
PLAYER_WALK_SPEED  = 5   # px/frame
PLAYER_JUMP_FORCE  = -14 # px/frame (negative = upward in Pygame's y-axis)

# Character-specific overrides (applied on top of the base values above)
LUNA_SPEED_BOOST      = 2    # extra px/frame during Luna's speed-boost ability
LUNA_DOUBLE_JUMP_FORCE = -12 # second-jump force (slightly weaker than first)

ORION_SUPER_JUMP_FORCE = -20  # px/frame — Orion's super jump
ORION_MAGNET_RADIUS    = 180  # px — radius within which Orion pulls platforms
ORION_FREEZE_DURATION  = 180  # frames (3 s at 60 FPS) platforms stay frozen

NOVA_DASH_SPEED        = 14   # px/frame — Nova's horizontal dash velocity
NOVA_DASH_DURATION     = 12   # frames the dash lasts
NOVA_SPARK_DURATION    = 300  # frames (5 s) Nova's spark trail remains active

# ---------------------------------------------------------------------------
# SPECIAL ABILITY COOLDOWNS  (in frames at 60 FPS)
# ---------------------------------------------------------------------------

COOLDOWN_LUNA_SHIELD  = 600   # 10 seconds
COOLDOWN_ORION_FREEZE = 480   # 8 seconds
COOLDOWN_NOVA_DASH    = 300   # 5 seconds

# ---------------------------------------------------------------------------
# PLAYER LIVES
# ---------------------------------------------------------------------------

PLAYER_LIVES = 5   # starting lives for each player

# ---------------------------------------------------------------------------
# PLATFORM SETTINGS
# ---------------------------------------------------------------------------

PLATFORM_WIDTH          = 120   # px — default platform width
PLATFORM_HEIGHT         = 18    # px — default platform height
PLATFORM_CRUMBLE_DELAY  = 45    # frames after landing before a crumbling platform breaks
MIN_PLATFORM_GAP        = 80    # px — minimum vertical gap between platforms (Level 2)
MAX_PLATFORM_GAP        = 120   # px — maximum vertical gap between platforms (Level 2)

# ---------------------------------------------------------------------------
# COMET / HAZARD SETTINGS
# ---------------------------------------------------------------------------

COMET_SPEED_MIN      = 3    # px/frame — slowest comet
COMET_SPEED_MAX      = 6    # px/frame — fastest comet
COMET_SPAWN_INTERVAL = 240  # frames between comet spawns (Level 1 baseline)
COMET_INTERVAL_L2_MIN = 120 # frames — minimum spawn interval in Level 2
                             # (difficulty ramps as the player climbs higher)
COMET_WIDTH          = 48   # px — hitbox / display size
COMET_HEIGHT         = 48   # px

# ---------------------------------------------------------------------------
COMET_INTERVAL_L2_VERY_RARE = 10 * FPS  # score 0-999: about one every 10 seconds
COMET_INTERVAL_L2_RARE      = 6 * FPS   # score 1000-1499: about one every 6 seconds

# MOONQUAKE SETTINGS
# ---------------------------------------------------------------------------

MOONQUAKE_INTERVAL      = 40 * FPS   # every 40 seconds (2400 frames at 60 FPS)
MOONQUAKE_SHAKE_MAGNITUDE = 8        # px — maximum screen-shake offset
MOONQUAKE_SHAKE_DURATION  = 90       # frames the screen shake lasts
MOONQUAKE_PLATFORM_SHIFT  = 14       # px — how far platforms are nudged horizontally

# ---------------------------------------------------------------------------
# CRYSTAL (LEVEL 1 WIN CONDITION)
# ---------------------------------------------------------------------------

CRYSTAL_Y_POSITION   = 80   # px from top of the level where the crystal is placed
CRYSTAL_FLASH_FRAMES = 60   # frames of white-flash effect on pickup
CRYSTAL_AURA_RADIUS  = 40   # px — green glow radius on pickup

# ---------------------------------------------------------------------------
# COLOURS
# Defined as (R, G, B) tuples; use TRANSPARENT as the colour key for surfaces
# that require per-pixel transparency.
# ---------------------------------------------------------------------------

WHITE       = (255, 255, 255)
BLACK       = (0,   0,   0  )
PURPLE      = (128, 0,   200)
PURPLE_DARK = (60,  0,   100)
CYAN        = (0,   255, 255)
CYAN_DARK   = (0,   180, 200)
GOLD        = (255, 200, 0  )
GREEN       = (0,   230, 80 )
RED         = (220, 30,  30 )
PINK        = (255, 80,  180)
BLUE        = (50,  120, 255)
GREY        = (140, 140, 150)
DARK_GREY   = (40,  40,  50 )
TRANSPARENT = (0,   0,   0  )  # used as colorkey on surfaces needing transparency

# Convenience aliases used by specific effects
COLOR_SHIELD    = CYAN          # Luna's shield bubble tint
COLOR_FREEZE    = (180, 220, 255)  # Orion's frozen-platform overlay
COLOR_SPARK     = GOLD          # Nova's spark trail colour
COLOR_MOONQUAKE = PURPLE        # screen-shake vignette tint
COLOR_COMET_EXP = PINK          # particle colour for comet explosion
COLOR_CRYSTAL   = (200, 255, 255)  # subtle blue-white crystal glow

# HUD colours
HUD_TEXT_COLOR  = WHITE
HUD_SHADOW_COLOR = DARK_GREY
HUD_BAR_BG      = DARK_GREY
HUD_BAR_FG      = CYAN

# ---------------------------------------------------------------------------
# PLAYER CONTROL BINDINGS
# ---------------------------------------------------------------------------

# Player 1 — WASD movement, G for special ability
P1_LEFT    = pygame.K_a
P1_RIGHT   = pygame.K_d
P1_JUMP    = pygame.K_w
P1_DOWN    = pygame.K_s    # crouch / drop through platform (future use)
P1_SPECIAL = pygame.K_g

# Player 2 — Arrow-key movement, L for special ability
P2_LEFT    = pygame.K_LEFT
P2_RIGHT   = pygame.K_RIGHT
P2_JUMP    = pygame.K_UP
P2_DOWN    = pygame.K_DOWN  # crouch / drop through platform (future use)
P2_SPECIAL = pygame.K_l

# ---------------------------------------------------------------------------
# CHARACTER IDs  (used as dictionary keys throughout the codebase)
# ---------------------------------------------------------------------------

CHAR_LUNA  = "luna"
CHAR_NOVA  = "nova"
CHAR_ORION = "orion"

# Ordered list for character-select cycling
CHARACTER_ORDER = [CHAR_LUNA, CHAR_NOVA, CHAR_ORION]

# Human-readable display names
CHARACTER_NAMES = {
    CHAR_LUNA:  "Luna",
    CHAR_NOVA:  "Nova",
    CHAR_ORION: "Orion",
}

# Short description shown on the character-select screen
CHARACTER_DESCRIPTIONS = {
    CHAR_LUNA: (
        "Balanced • Double Jump • Speed Boost\n"
        "Special: Shield Bubble — blocks one comet"
    ),
    CHAR_NOVA: (
        "Fast • Quick Dash • Agile\n"
        "Special: Spark Trail — reveals hidden platforms"
    ),
    CHAR_ORION: (
        "High Jumper • Super Jump • Magnet Pull\n"
        "Special: Platform Freeze — locks platforms in place"
    ),
}

# ---------------------------------------------------------------------------
# UI / FONT SETTINGS
# ---------------------------------------------------------------------------

FONT_SIZE_LARGE  = 48   # title text
FONT_SIZE_MEDIUM = 32   # menus, headings
FONT_SIZE_SMALL  = 22   # HUD values, descriptions
FONT_SIZE_TINY   = 16   # tooltips, cooldown counters

# ---------------------------------------------------------------------------
# LEVEL 2 — ENDLESS ASCENT SPECIFICS
# ---------------------------------------------------------------------------

L2_HIDDEN_PLATFORM_CHANCE = 0.10   # 10 % of platforms in Level 2 are hidden
L2_SCORE_PER_PLATFORM     = 10     # points awarded per platform passed
L2_COMET_RAMP_HEIGHT      = 500    # px climbed before comet frequency starts increasing
L2_COMET_RAMP_STEP        = 100    # px — every additional step, interval shrinks by 1 frame

# ---------------------------------------------------------------------------
# AUDIO SETTINGS
# ---------------------------------------------------------------------------

MUSIC_VOLUME = 0.6   # 0.0 – 1.0
SFX_VOLUME   = 0.85  # 0.0 – 1.0
