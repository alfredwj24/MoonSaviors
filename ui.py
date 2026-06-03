"""
ui.py — Moon Saviors
====================
All user-interface screens and in-game HUD elements.

Screens implemented
-------------------
  MainMenu            — title screen with Start / Quit buttons
  CharacterSelectScreen — two-player character picker with card UI
  HUD                 — in-game overlay (lives, crystals, score)
  GameOverScreen      — end screen with score summary and retry/menu buttons
  WinScreen           — victory screen with green aura and level-2 prompt

University report note:
  All screens follow the same three-method contract used by the level classes:
      handle_event(event)  → process a single pygame.event.Event
      update()             → advance animations / timers by one frame
      draw(surface)        → render current state onto *surface*
  This uniformity lets main.py switch between screens without knowing their
  internal details — it calls the same three methods regardless of which
  screen is active.
"""

import pygame
import math
import os

from config import (
    # Screen
    SCREEN_WIDTH, SCREEN_HEIGHT,
    # Asset paths — backgrounds
    BG_LEVEL1, BG_CHARACTER_SELECT,
    # Asset paths — characters
    SPRITE_LUNA, SPRITE_NOVA, SPRITE_ORION,
    # Asset paths — HUD / UI
    ICON_LIFE_COUNTER, ICON_CRYSTAL_HUD,
    # Asset paths — music / sfx (+ global SFX volume)
    MUSIC_CHARACTER_SELECT, SFX_VICTORY, SFX_VOLUME,
    # Colours
    WHITE, BLACK, PURPLE, CYAN, CYAN_DARK, GOLD, GREEN, RED,
    PURPLE_DARK, PINK, BLUE, GREY, DARK_GREY, COLOR_CRYSTAL,
    # Font sizes
    FONT_SIZE_LARGE, FONT_SIZE_MEDIUM, FONT_SIZE_SMALL, FONT_SIZE_TINY,
    # Game states
    STATE_LEVEL1, STATE_LEVEL2, STATE_GAME_OVER, STATE_MENU,
    # Character IDs and metadata
    CHAR_LUNA, CHAR_NOVA, CHAR_ORION,
    CHARACTER_ORDER, CHARACTER_NAMES, CHARACTER_DESCRIPTIONS,
    # Controls (for character select)
    P1_LEFT, P1_RIGHT, P1_JUMP,
    P2_LEFT, P2_RIGHT, P2_JUMP,
    # Player lives
    PLAYER_LIVES,
    # FPS
    FPS,
)
from effects import ParticleSystem, ScreenEffect


# ---------------------------------------------------------------------------
# MODULE-LEVEL HELPERS
# ---------------------------------------------------------------------------

def _load_image(path: str, size: tuple | None = None) -> pygame.Surface:
    """
    Load an image asset, scaling to *size* if given.
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
    """Load a sound file; return None silently if missing."""
    try:
        snd = pygame.mixer.Sound(path)
        snd.set_volume(SFX_VOLUME)
        return snd
    except (FileNotFoundError, pygame.error):
        return None


def _start_music(path: str, volume: float = 0.6) -> None:
    """Stream looping background music; skip silently if file is absent."""
    try:
        pygame.mixer.music.load(path)
        pygame.mixer.music.set_volume(volume)
        pygame.mixer.music.play(-1)
    except (FileNotFoundError, pygame.error):
        pass


def _make_font(size: int, bold: bool = False) -> pygame.font.Font:
    """
    Return a pygame font.

    Preference order:
      1. 'Press Start 2P'  — a built-in pixel-style font on many systems.
      2. 'monospace'       — reliable fallback available everywhere.
      3. pygame default    — last resort.

    University report:
      Trying multiple font names with a graceful fallback ensures the game
      looks correct on the marker's machine regardless of which system fonts
      are installed.
    """
    for name in ("Press Start 2P", "monospace", None):
        try:
            if name is None:
                return pygame.font.Font(None, size)
            return pygame.font.SysFont(name, size, bold=bold)
        except Exception:
            continue
    return pygame.font.Font(None, size)


def _draw_text(surface, text, font, color, cx, cy,
               shadow=True, shadow_color=BLACK, shadow_offset=(2, 2)):
    """
    Render *text* centred at (cx, cy) with an optional drop shadow.

    University report:
      Drawing a shadow (identical text rendered in a dark colour a few
      pixels offset) greatly improves legibility over busy backgrounds
      without requiring a dedicated text-box panel.
    """
    if shadow:
        shadow_surf = font.render(text, True, shadow_color)
        sr = shadow_surf.get_rect(center=(cx + shadow_offset[0],
                                          cy + shadow_offset[1]))
        surface.blit(shadow_surf, sr)
    text_surf = font.render(text, True, color)
    tr = text_surf.get_rect(center=(cx, cy))
    surface.blit(text_surf, tr)
    return tr   # return rect so callers can check bounds / highlight


class _Button:
    """
    A simple rectangular button used across all menu screens.

    Hover detection is done via pygame.Rect.collidepoint each draw call.
    The button does not depend on mouse input — it can also be keyboard-
    navigated by setting .selected = True from outside.
    """

    PAD_X = 40
    PAD_Y = 14

    def __init__(self, text: str, cx: int, cy: int,
                 font: pygame.font.Font,
                 color_normal=CYAN_DARK,
                 color_hover=CYAN,
                 text_color=WHITE):
        self.text         = text
        self.font         = font
        self.color_normal = color_normal
        self.color_hover  = color_hover
        self.text_color   = text_color
        self.selected     = False   # True when keyboard focus is on this button

        # Measure text to size the button rectangle
        tw, th      = font.size(text)
        w           = tw + self.PAD_X * 2
        h           = th + self.PAD_Y * 2
        self.rect   = pygame.Rect(0, 0, w, h)
        self.rect.center = (cx, cy)

        # Pulse animation offset (used when selected)
        self._pulse: float = 0.0

    def update(self) -> None:
        """Advance hover-pulse animation."""
        self._pulse += 0.08

    def draw(self, surface: pygame.Surface,
             mouse_pos: tuple | None = None) -> None:
        """
        Render the button.

        Hover state: mouse overlaps OR self.selected is True.
        Hover draws the button slightly larger with a lighter colour and a
        glowing border, giving clear visual feedback.
        """
        hovered = self.selected or (
            mouse_pos is not None and self.rect.collidepoint(mouse_pos)
        )

        # ---- Glow border when hovered ----
        if hovered:
            alpha  = int(160 + 80 * math.sin(self._pulse))
            border = pygame.Surface(
                (self.rect.w + 8, self.rect.h + 8), pygame.SRCALPHA
            )
            border.fill((*self.color_hover, alpha))
            surface.blit(border, (self.rect.x - 4, self.rect.y - 4))

        # ---- Button body ----
        color = self.color_hover if hovered else self.color_normal
        pygame.draw.rect(surface, color, self.rect, border_radius=8)
        pygame.draw.rect(surface, WHITE, self.rect, width=2, border_radius=8)

        # ---- Label ----
        _draw_text(surface, self.text, self.font,
                   self.text_color, *self.rect.center)

    def is_clicked(self, event: pygame.event.Event,
                   mouse_pos: tuple | None = None) -> bool:
        """
        Return True if this button was activated in *event*.

        Activation = left mouse click inside rect OR pygame.KEYDOWN with
        RETURN/KP_ENTER while self.selected is True.
        """
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if mouse_pos and self.rect.collidepoint(mouse_pos):
                return True
        if event.type == pygame.KEYDOWN and self.selected:
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                return True
        return False


# ---------------------------------------------------------------------------
# MAIN MENU
# ---------------------------------------------------------------------------

class MainMenu:
    """
    The title screen shown when the game first launches.

    Elements
    --------
    • Full-screen Level 1 background for atmosphere.
    • "MOON SAVIORS" title with a pulsing cyan glow effect.
    • Two buttons: Start Game, Quit.
    • Subtle starfield particle system in the background.

    University report:
      The pulsing title is implemented with a sine-wave alpha applied to a
      second copy of the title text rendered in CYAN.  Both copies are blitted
      at the same position; the glow copy's alpha oscillates so the title
      appears to breathe with light.
    """

    def __init__(self):
        # ---- Fonts ----
        self._font_title  = _make_font(FONT_SIZE_LARGE,  bold=True)
        self._font_sub    = _make_font(FONT_SIZE_MEDIUM, bold=False)
        self._font_btn    = _make_font(FONT_SIZE_SMALL,  bold=True)

        # ---- Background ----
        self._bg = _load_image(BG_LEVEL1, (SCREEN_WIDTH, SCREEN_HEIGHT))

        # ---- Dark overlay (improves contrast over the busy background) ----
        self._overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        self._overlay.fill((0, 0, 0, 120))

        # ---- Buttons ----
        btn_cx = SCREEN_WIDTH // 2
        self._btn_level1 = _Button("LEVEL 1: CRYSTAL", btn_cx, 520, self._font_btn)
        self._btn_level2 = _Button("LEVEL 2: ARCADE",  btn_cx, 590, self._font_btn,
                                   color_normal=PURPLE_DARK,
                                   color_hover=PURPLE)
        self._btn_quit   = _Button("QUIT",             btn_cx, 660, self._font_btn)
        self._focused    = 0
        self._buttons    = [self._btn_level1, self._btn_level2, self._btn_quit]
        self._buttons[self._focused].selected = True

        # ---- Title pulse state ----
        self._pulse: float = 0.0

        # ---- Outcome ----
        # main.py reads this each frame.  None = no action taken yet.
        self.next_state: str | None = None

        # ---- Decorative particles (simulate drifting moon dust) ----
        self._particles = ParticleSystem()
        self._dust_timer = 0

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> None:
        """
        Route keyboard and mouse events to the appropriate button action.

        Keyboard navigation:
          DOWN / S   → move focus to next button
          UP   / W   → move focus to previous button
          ENTER      → activate focused button
        """
        mouse = pygame.mouse.get_pos()

        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_DOWN, pygame.K_s):
                self._set_focus((self._focused + 1) % len(self._buttons))
            elif event.key in (pygame.K_UP, pygame.K_w):
                self._set_focus((self._focused - 1) % len(self._buttons))

        if self._btn_level1.is_clicked(event, mouse):
            self.next_state = STATE_LEVEL1

        if self._btn_level2.is_clicked(event, mouse):
            self.next_state = STATE_LEVEL2

        if self._btn_quit.is_clicked(event, mouse):
            self.next_state = "QUIT"

    def update(self) -> None:
        """Advance pulse animation, decorative particles, and button hover."""
        self._pulse += 0.05

        # Scatter a few dust particles from the bottom of the screen
        self._dust_timer += 1
        if self._dust_timer >= 12:
            self._dust_timer = 0
            import random
            self._particles.landing_dust(
                (random.randint(0, SCREEN_WIDTH),
                 SCREEN_HEIGHT - 10)
            )
        self._particles.update()

        for btn in self._buttons:
            btn.update()

    def draw(self, surface: pygame.Surface) -> None:
        """Render background, overlay, title, subtitle, particles, buttons."""
        # ---- Background ----
        surface.blit(self._bg, (0, 0))
        surface.blit(self._overlay, (0, 0))

        # ---- Decorative particles ----
        self._particles.draw(surface)

        # ---- Title glow (CYAN copy, pulsing alpha) ----
        glow_alpha = int(120 + 100 * math.sin(self._pulse))
        title_glow = self._font_title.render("MOON SAVIORS", True, CYAN)
        title_glow.set_alpha(glow_alpha)
        gr = title_glow.get_rect(center=(SCREEN_WIDTH // 2 + 2, 202))
        surface.blit(title_glow, gr)

        # ---- Title (solid white on top) ----
        _draw_text(surface, "MOON SAVIORS", self._font_title,
                   WHITE, SCREEN_WIDTH // 2, 200,
                   shadow=True, shadow_offset=(3, 3))

        # ---- Subtitle ----
        _draw_text(surface, "CHOOSE A MISSION",
                   self._font_sub, CYAN,
                   SCREEN_WIDTH // 2, 270)

        # ---- Controls hint ----
        _draw_text(surface, "P1: WASD + G  |  P2: ARROWS + L",
                   _make_font(FONT_SIZE_TINY), GREY,
                   SCREEN_WIDTH // 2, 310)

        # ---- Buttons ----
        mouse = pygame.mouse.get_pos()
        for btn in self._buttons:
            btn.draw(surface, mouse)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _set_focus(self, idx: int) -> None:
        """Move keyboard focus to button at *idx*."""
        self._buttons[self._focused].selected = False
        self._focused = idx
        self._buttons[self._focused].selected = True


# ---------------------------------------------------------------------------
# CHARACTER SELECT SCREEN
# ---------------------------------------------------------------------------

# Card layout constants
_CARD_W  = 190
_CARD_H  = 380
_CARD_Y  = SCREEN_HEIGHT // 2 - _CARD_H // 2 + 20
_CARD_GAP = 28
_CARD_START_X = (SCREEN_WIDTH - (_CARD_W * 3 + _CARD_GAP * 2)) // 2
_CARD_XS = [
    _CARD_START_X,
    _CARD_START_X + _CARD_W + _CARD_GAP,
    _CARD_START_X + (_CARD_W + _CARD_GAP) * 2,
]

# Colour theme per character (used for card border and ability tags)
_CHAR_COLORS = {
    CHAR_LUNA:  CYAN,
    CHAR_ORION: GOLD,
    CHAR_NOVA:  PINK,
}

# Playstyle tags shown on each card
_CHAR_TAGS = {
    CHAR_LUNA:  "BALANCED",
    CHAR_ORION: "HIGH JUMPER",
    CHAR_NOVA:  "SPEEDSTER",
}

# Ability bullet lines per character (short, card-friendly)
_CHAR_ABILITIES = {
    CHAR_LUNA: [
        "• Double Jump",
        "• Speed Boost",
        "• [G] Shield Bubble",
        "  Blocks 1 comet",
    ],
    CHAR_ORION: [
        "• Super Jump (1.8×)",
        "• Magnet Pull",
        "• [G] Platform Freeze",
        "  Locks nearby tiles",
    ],
    CHAR_NOVA: [
        "• 1.5× Move Speed",
        "• Quick Dash",
        "• [G] Spark Trail",
        "  Reveals hidden tiles",
    ],
}


class CharacterSelectScreen:
    """
    Two-player character selection screen.

    Layout
    ------
    Three character cards are displayed side by side.  Each card shows:
      • Character sprite (scaled to fit the card)
      • Character name
      • Playstyle tag (e.g. "SPEEDSTER")
      • Ability bullet list

    Player 1 (WASD + ENTER) and Player 2 (ARROW KEYS + ENTER) independently
    browse and confirm their picks.  The same character cannot be selected by
    both players — if Player 2 lands on the same card as Player 1 and tries
    to confirm, a warning message is shown.

    University report — dual-cursor design:
      Each player has an independent cursor index (0–2) into CHARACTER_ORDER.
      Confirmed picks are stored separately.  The `_can_proceed` property
      returns True only when both are confirmed AND differ.  This is checked
      before emitting the 'PROCEED' event so main.py never receives an invalid
      selection pair.
    """

    def __init__(self, target_state: str = STATE_LEVEL1):
        # ---- Fonts ----
        self._font_title   = _make_font(FONT_SIZE_MEDIUM, bold=True)
        self._font_name    = _make_font(FONT_SIZE_SMALL,  bold=True)
        self._font_tag     = _make_font(FONT_SIZE_TINY,   bold=False)
        self._font_ability = _make_font(FONT_SIZE_TINY,   bold=False)

        # ---- Background ----
        self._bg = _load_image(BG_CHARACTER_SELECT, (SCREEN_WIDTH, SCREEN_HEIGHT))
        self._overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        self._overlay.fill((0, 0, 0, 100))

        # ---- Sprite images (keyed by character ID) ----
        self._sprites = {
            CHAR_LUNA:  _load_image(SPRITE_LUNA,  (120, 160)),
            CHAR_ORION: _load_image(SPRITE_ORION, (120, 160)),
            CHAR_NOVA:  _load_image(SPRITE_NOVA,  (120, 160)),
        }

        # ---- Player cursor state ----
        # Cursor index into CHARACTER_ORDER list
        self._p1_cursor:    int       = 0
        self._p2_cursor:    int       = 2    # start on opposite end so defaults differ
        self._p1_confirmed: bool      = False
        self._p2_confirmed: bool      = False
        self._p1_choice:    str | None = None   # character ID once confirmed
        self._p2_choice:    str | None = None

        # ---- Warning message ----
        self._warning:       str = ""
        self._warning_timer: int = 0   # frames to show warning

        # ---- Border pulse state (per card) ----
        self._pulse: float = 0.0

        # ---- Outcome ----
        self.next_state: str | None = None
        self.p1_character: str | None = None
        self.p2_character: str | None = None
        self._target_state = target_state

        # ---- Music ----
        _start_music(MUSIC_CHARACTER_SELECT, volume=0.55)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> None:
        """
        Route key events to the correct player's cursor.

        Player 1 — A/D to browse, W/ENTER to confirm.
        Player 2 — LEFT/RIGHT to browse, UP/ENTER to confirm.

        University report:
          Confirming is only allowed on KEYDOWN events (edge-detect), not
          while the key is held, preventing accidental double-confirmation.
          We use the `_p1_confirmed` / `_p2_confirmed` flags so a player can
          browse freely before locking in.  Once confirmed, movement keys are
          ignored for that player.
        """
        if event.type != pygame.KEYDOWN:
            return

        # ---- Player 1 input ----
        if not self._p1_confirmed:
            if event.key == P1_LEFT:
                self._p1_cursor = (self._p1_cursor - 1) % len(CHARACTER_ORDER)
            elif event.key == P1_RIGHT:
                self._p1_cursor = (self._p1_cursor + 1) % len(CHARACTER_ORDER)
            elif event.key in (pygame.K_RETURN, pygame.K_g, P1_JUMP):
                self._try_confirm_p1()
        else:
            # Allow P1 to cancel their selection with Backspace
            if event.key == pygame.K_BACKSPACE:
                self._p1_confirmed = False
                self._p1_choice    = None

        # ---- Player 2 input ----
        if not self._p2_confirmed:
            if event.key == P2_LEFT:
                self._p2_cursor = (self._p2_cursor - 1) % len(CHARACTER_ORDER)
            elif event.key == P2_RIGHT:
                self._p2_cursor = (self._p2_cursor + 1) % len(CHARACTER_ORDER)
            elif event.key in (pygame.K_RETURN, pygame.K_l, P2_JUMP):
                self._try_confirm_p2()
        else:
            if event.key == pygame.K_BACKSPACE:
                self._p2_confirmed = False
                self._p2_choice    = None

        # ---- Proceed check ----
        if self._can_proceed:
            self.p1_character = self._p1_choice
            self.p2_character = self._p2_choice
            self.next_state   = self._target_state

    def update(self) -> None:
        """Advance animation timers."""
        self._pulse += 0.07
        if self._warning_timer > 0:
            self._warning_timer -= 1
        else:
            self._warning = ""

    def draw(self, surface: pygame.Surface) -> None:
        """
        Render the full character-select screen.

        Draw order:
          1. Background + overlay
          2. Title
          3. Character cards (with highlighted borders for P1/P2 cursors)
          4. Confirm status bar at the bottom
          5. Warning message (if any)
        """
        # ---- 1. Background ----
        surface.blit(self._bg, (0, 0))
        surface.blit(self._overlay, (0, 0))

        # ---- 2. Title ----
        _draw_text(surface, "CHOOSE YOUR ASTRONAUT",
                   self._font_title, WHITE,
                   SCREEN_WIDTH // 2, 48)

        _draw_text(surface, "P1: A/D + ENTER          P2: ARROWS + ENTER",
                   self._font_tag, GREY,
                   SCREEN_WIDTH // 2, 82)

        # ---- 3. Cards ----
        for i, char_id in enumerate(CHARACTER_ORDER):
            self._draw_card(surface, i, char_id)

        # ---- 4. Confirm status ----
        self._draw_confirm_bar(surface)

        # ---- 5. Warning ----
        if self._warning and self._warning_timer > 0:
            _draw_text(surface, self._warning,
                       self._font_tag, RED,
                       SCREEN_WIDTH // 2, SCREEN_HEIGHT - 30)

    # ------------------------------------------------------------------
    # Private draw helpers
    # ------------------------------------------------------------------

    def _draw_card(self, surface: pygame.Surface,
                   card_idx: int, char_id: str) -> None:
        """
        Render one character card at position *card_idx*.

        A card consists of:
          • Semi-transparent dark panel (background)
          • Glowing coloured border if this card is hovered or confirmed
          • Character sprite centred in the upper portion
          • Name, playstyle tag, ability list below

        University report — layered surface technique:
          The card panel is drawn as an SRCALPHA surface filled with a dark
          colour at partial alpha, then blitted to the screen.  This creates a
          frosted-glass panel effect.  The glow border is a slightly larger
          SRCALPHA rect blitted before the panel so it appears behind the panel
          edges.
        """
        x  = _CARD_XS[card_idx]
        y  = _CARD_Y
        w  = _CARD_W
        h  = _CARD_H
        cx = x + w // 2
        char_color = _CHAR_COLORS[char_id]

        # Determine border state
        p1_here      = (self._p1_cursor == card_idx)
        p2_here      = (self._p2_cursor == card_idx)
        p1_confirmed = (self._p1_confirmed and self._p1_choice == char_id)
        p2_confirmed = (self._p2_confirmed and self._p2_choice == char_id)
        any_hover    = p1_here or p2_here

        # ---- Glow border ----
        if any_hover or p1_confirmed or p2_confirmed:
            # Pulse alpha between 140 and 255
            alpha = int(180 + 75 * math.sin(self._pulse))
            border_surf = pygame.Surface((w + 12, h + 12), pygame.SRCALPHA)
            border_surf.fill((*char_color, alpha))
            surface.blit(border_surf, (x - 6, y - 6))

        # ---- Card panel ----
        panel = pygame.Surface((w, h), pygame.SRCALPHA)
        panel.fill((10, 5, 25, 210))   # very dark purple, mostly opaque
        surface.blit(panel, (x, y))
        pygame.draw.rect(surface, char_color,
                         pygame.Rect(x, y, w, h), width=2, border_radius=6)

        # ---- P1 / P2 cursor labels ----
        label_y = y - 22
        if p1_here or p1_confirmed:
            lbl = "P1 ✓" if p1_confirmed else "P1"
            lbl_surf = self._font_tag.render(lbl, True, CYAN)
            surface.blit(lbl_surf, (x + 4, label_y))
        if p2_here or p2_confirmed:
            lbl = "P2 ✓" if p2_confirmed else "P2"
            lbl_surf = self._font_tag.render(lbl, True, GOLD)
            lr = lbl_surf.get_rect(right=x + w - 4, y=label_y)
            surface.blit(lbl_surf, lr)

        # ---- Sprite ----
        sprite = self._sprites[char_id]
        sr     = sprite.get_rect(centerx=cx, top=y + 12)
        surface.blit(sprite, sr)

        # ---- Name ----
        name_y = y + 12 + 160 + 14
        _draw_text(surface, CHARACTER_NAMES[char_id].upper(),
                   self._font_name, char_color, cx, name_y)

        # ---- Playstyle tag ----
        tag_y = name_y + 26
        tag_surf = self._font_tag.render(_CHAR_TAGS[char_id], True, WHITE)
        tag_bg   = pygame.Surface(
            (tag_surf.get_width() + 12, tag_surf.get_height() + 6),
            pygame.SRCALPHA,
        )
        tag_bg.fill((*char_color, 80))
        tbr = tag_bg.get_rect(centerx=cx, top=tag_y)
        surface.blit(tag_bg, tbr)
        _draw_text(surface, _CHAR_TAGS[char_id],
                   self._font_tag, WHITE, cx, tag_y + tag_surf.get_height() // 2 + 3,
                   shadow=False)

        # ---- Abilities ----
        ability_y = tag_y + 30
        for line in _CHAR_ABILITIES[char_id]:
            ability_surf = self._font_ability.render(line, True, GREY)
            surface.blit(ability_surf, (x + 10, ability_y))
            ability_y += self._font_ability.get_linesize() + 2

    def _draw_confirm_bar(self, surface: pygame.Surface) -> None:
        """
        Render the bottom-of-screen confirmation status for both players.

        Shows:
          • "P1: [CHARACTER]  ✓" in cyan when confirmed, browsing hint otherwise.
          • "P2: [CHARACTER]  ✓" in gold  when confirmed, browsing hint otherwise.
          • "PRESS ENTER TO CONFIRM" prompt when at least one player is not done.
          • "BOTH PLAYERS READY!" when both are confirmed on different characters.
        """
        bar_y    = SCREEN_HEIGHT - 80
        font     = self._font_tag
        p1_char  = CHARACTER_ORDER[self._p1_cursor]
        p2_char  = CHARACTER_ORDER[self._p2_cursor]

        # P1 status
        if self._p1_confirmed:
            p1_text  = f"P1: {CHARACTER_NAMES[self._p1_choice]} ✓"
            p1_color = CYAN
        else:
            p1_text  = f"P1: {CHARACTER_NAMES[p1_char]}  (ENTER to lock)"
            p1_color = GREY

        p1_surf = font.render(p1_text, True, p1_color)
        surface.blit(p1_surf, (20, bar_y))

        # P2 status
        if self._p2_confirmed:
            p2_text  = f"P2: {CHARACTER_NAMES[self._p2_choice]} ✓"
            p2_color = GOLD
        else:
            p2_text  = f"P2: {CHARACTER_NAMES[p2_char]}  (ENTER to lock)"
            p2_color = GREY

        p2_surf = font.render(p2_text, True, p2_color)
        p2r = p2_surf.get_rect(right=SCREEN_WIDTH - 20, y=bar_y)
        surface.blit(p2_surf, p2r)

        # ---- Centre prompt ----
        if self._can_proceed:
            prompt_text  = "BOTH PLAYERS READY!  Starting..."
            prompt_color = GREEN
        else:
            prompt_text  = "PRESS ENTER TO CONFIRM"
            prompt_alpha = int(180 + 75 * math.sin(self._pulse * 1.5))
            prompt_color = WHITE

        prompt_surf = font.render(prompt_text, True,
                                  GREEN if self._can_proceed else WHITE)
        if not self._can_proceed:
            prompt_surf.set_alpha(int(180 + 75 * math.sin(self._pulse * 1.5)))
        pr = prompt_surf.get_rect(center=(SCREEN_WIDTH // 2, bar_y + 26))
        surface.blit(prompt_surf, pr)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _try_confirm_p1(self) -> None:
        """Validate and lock in Player 1's current cursor choice."""
        chosen = CHARACTER_ORDER[self._p1_cursor]
        if self._p2_confirmed and self._p2_choice == chosen:
            self._warning       = "P1: Character taken! Choose another."
            self._warning_timer = 3 * FPS
            return
        self._p1_confirmed = True
        self._p1_choice    = chosen

    def _try_confirm_p2(self) -> None:
        """Validate and lock in Player 2's current cursor choice."""
        chosen = CHARACTER_ORDER[self._p2_cursor]
        if self._p1_confirmed and self._p1_choice == chosen:
            self._warning       = "P2: Character taken! Choose another."
            self._warning_timer = 3 * FPS
            return
        self._p2_confirmed = True
        self._p2_choice    = chosen

    @property
    def _can_proceed(self) -> bool:
        """True when both players have confirmed different characters."""
        return (
            self._p1_confirmed and self._p2_confirmed
            and self._p1_choice != self._p2_choice
        )


# ---------------------------------------------------------------------------
# HUD
# ---------------------------------------------------------------------------

class HUD:
    """
    In-game heads-up display.

    Elements
    --------
    Top-left  : Player 1 name + life-counter icons.
    Top-right : Player 2 name + life-counter icons.
    Bottom-centre : Crystal count with HUD icon (both players summed).
    Level 2 only  : Height score + high score at top-centre.

    University report — icon-based life display:
      The life-counter icon (a small helmet sprite) is blitted N times
      horizontally for N remaining lives.  When lives decrease, fewer icons
      are drawn without any animation state being needed — the number of blits
      is simply min(player.lives, PLAYER_LIVES).  This is a classic technique
      used in retro games (Super Mario Bros, Zelda) because it is immediately
      readable at a glance.
    """

    ICON_SIZE   = (24, 24)   # px — life icon display size
    ICON_GAP    = 4          # px — gap between life icons
    HUD_MARGIN  = 10         # px — edge margin

    def __init__(self, p1_name: str = "PLAYER 1", p2_name: str = "PLAYER 2"):
        self._p1_name = p1_name.upper()
        self._p2_name = p2_name.upper()

        # ---- Fonts ----
        self._font_name  = _make_font(FONT_SIZE_TINY, bold=True)
        self._font_score = _make_font(FONT_SIZE_TINY, bold=False)

        # ---- Icons ----
        self._life_icon    = _load_image(ICON_LIFE_COUNTER, self.ICON_SIZE)
        self._crystal_icon = _load_image(ICON_CRYSTAL_HUD,  (28, 28))

        # ---- Faded life icon (for lost lives, shown as dim ghost) ----
        self._life_icon_dim = self._life_icon.copy()
        self._life_icon_dim.set_alpha(50)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def draw(self, surface: pygame.Surface,
             player1, player2,
             level_type: str = STATE_LEVEL1,
             score: int = 0,
             high_score: int = 0) -> None:
        """
        Render the full HUD for the current frame.

        Parameters
        ----------
        surface    : The game screen surface.
        player1    : Player instance (P1).
        player2    : Player instance (P2).
        level_type : STATE_LEVEL1 or STATE_LEVEL2 from config.py.
        score      : Current score (Level 2 only).
        high_score : Best score (Level 2 only).
        """
        # ---- Semi-transparent HUD strip at top ----
        self._draw_top_strip(surface)

        # ---- Player 1 — top left ----
        self._draw_player_hud(surface, player1, side="left")

        # ---- Player 2 — top right ----
        self._draw_player_hud(surface, player2, side="right")

        # ---- Crystal count — bottom centre ----
        self._draw_crystal_count(surface, player1, player2)

        # ---- Level 2 score — top centre ----
        if level_type == STATE_LEVEL2:
            self._draw_level2_score(surface, score, high_score)

    # ------------------------------------------------------------------
    # Private draw helpers
    # ------------------------------------------------------------------

    def _draw_top_strip(self, surface: pygame.Surface) -> None:
        """
        Draw a semi-transparent dark bar across the top of the screen.

        University report:
          The strip provides a neutral background for HUD text so it remains
          legible regardless of the level background behind it.  Using
          SRCALPHA allows the level to bleed through slightly, keeping the
          sense of depth without obscuring the gameplay area below.
        """
        strip = pygame.Surface((SCREEN_WIDTH, 56), pygame.SRCALPHA)
        strip.fill((0, 0, 10, 160))
        surface.blit(strip, (0, 0))

    def _draw_player_hud(self, surface: pygame.Surface,
                          player, side: str) -> None:
        """
        Render one player's name and life icons.

        Parameters
        ----------
        player : Player instance.
        side   : 'left' for P1, 'right' for P2.
        """
        m = self.HUD_MARGIN
        y = m + 2

        name_color = CYAN if side == "left" else GOLD

        # ---- Name ----
        char_name = getattr(player, '__class__', None)
        char_name = char_name.__name__.upper() if char_name else "PLAYER"
        display   = f"{'P1' if side == 'left' else 'P2'}: {char_name}"

        if side == "left":
            name_surf = self._font_name.render(display, True, name_color)
            surface.blit(name_surf, (m, y))
            icon_start_x = m
            icon_y       = y + name_surf.get_height() + 4
        else:
            name_surf = self._font_name.render(display, True, name_color)
            name_r    = name_surf.get_rect(right=SCREEN_WIDTH - m, y=y)
            surface.blit(name_surf, name_r)
            # Icons drawn right-to-left from right edge
            icon_y = y + name_surf.get_height() + 4
            total_icon_w = (PLAYER_LIVES * (self.ICON_SIZE[0] + self.ICON_GAP)
                            - self.ICON_GAP)
            icon_start_x = SCREEN_WIDTH - m - total_icon_w

        # ---- Life icons ----
        # Draw all PLAYER_LIVES slots; fill with dim icon for lost lives.
        lives_remaining = max(0, player.lives)
        for i in range(PLAYER_LIVES):
            ix = icon_start_x + i * (self.ICON_SIZE[0] + self.ICON_GAP)
            icon = self._life_icon if i < lives_remaining else self._life_icon_dim
            surface.blit(icon, (ix, icon_y))

        # ---- Special-ability readiness ----
        # Show the player's special status next to their lives so they know
        # at a glance when their [G] / [L] power is charged.
        total_icon_w = (PLAYER_LIVES * (self.ICON_SIZE[0] + self.ICON_GAP)
                        - self.ICON_GAP)
        info = self._special_text(player, side)
        if info:
            txt, col = info
            tsurf = self._font_name.render(txt, True, col)
            ty = icon_y + (self.ICON_SIZE[1] - tsurf.get_height()) // 2
            if side == "left":
                surface.blit(tsurf, (icon_start_x + total_icon_w + 10, ty))
            else:
                tr = tsurf.get_rect(right=icon_start_x - 10, y=ty)
                surface.blit(tsurf, tr)

    def _special_text(self, player, side: str):
        """
        Return (text, colour) describing this player's special-ability state, or
        None for a character with no readable cooldown.

        Each character exposes a *_cooldown_pct property (1.0 = just used,
        0.0 = ready); Luna/Orion/Nova also expose an "active" flag.  We surface
        that as a short HUD tag so players can see when their [G]/[L] power is
        charged instead of guessing.
        """
        key = "G" if side == "left" else "L"
        if hasattr(player, "shield_cooldown_pct"):
            label = "SHIELD"
            active = getattr(player.shield, "active", False)
            pct    = player.shield_cooldown_pct
        elif hasattr(player, "freeze_cooldown_pct"):
            label, active, pct = "FREEZE", player.freeze_active, player.freeze_cooldown_pct
        elif hasattr(player, "trail_cooldown_pct"):
            label, active, pct = "SPARK", player.trail_active, player.trail_cooldown_pct
        else:
            return None

        if active:
            return (f"{label} ON", GREEN)
        if pct <= 0:
            return (f"[{key}] {label}", CYAN if side == "left" else GOLD)
        return (f"{label} {int((1 - pct) * 100)}%", GREY)

    def _draw_crystal_count(self, surface: pygame.Surface,
                              p1, p2) -> None:
        """
        Render the crystal icon + combined crystal count at the bottom centre.

        University report:
          Crystal counts from both players are summed so the HUD shows
          collective team progress.  The icon-plus-number layout (icon on
          left, number on right) is instantly recognisable as a resource
          counter from any action game.
        """
        total_crystals = getattr(p1, "crystals", 0) + getattr(p2, "crystals", 0)

        icon_w, icon_h = 28, 28
        text_surf = self._font_score.render(
            f"× {total_crystals}", True, COLOR_CRYSTAL
        )
        total_w = icon_w + 6 + text_surf.get_width()
        start_x = SCREEN_WIDTH // 2 - total_w // 2
        y       = SCREEN_HEIGHT - icon_h - 12

        # Strip behind crystal HUD
        strip = pygame.Surface((total_w + 24, icon_h + 12), pygame.SRCALPHA)
        strip.fill((0, 0, 10, 140))
        surface.blit(strip, (start_x - 12, y - 6))

        surface.blit(self._crystal_icon, (start_x, y))
        surface.blit(text_surf, (start_x + icon_w + 6,
                                  y + icon_h // 2 - text_surf.get_height() // 2))

    def _draw_level2_score(self, surface: pygame.Surface,
                            score: int, high_score: int) -> None:
        """
        Render score and high score in the top centre (Level 2 only).

        University report:
          Centralising the score in Level 2 (rather than a corner) emphasises
          that it is the primary objective — there is no win condition, so the
          score is what the players are chasing.
        """
        font = self._font_score
        cx   = SCREEN_WIDTH // 2

        score_text = font.render(f"SCORE: {score}", True, GOLD)
        hi_text    = font.render(f"BEST: {high_score}", True, CYAN)

        # Drop shadows
        _draw_text(surface, f"SCORE: {score}",    font, GOLD, cx, 18)
        _draw_text(surface, f"BEST:  {high_score}", font, CYAN, cx, 36)


# ---------------------------------------------------------------------------
# GAME OVER SCREEN
# ---------------------------------------------------------------------------

class GameOverScreen:
    """
    Displayed when both players have lost all their lives.

    Elements
    --------
    • "GAME OVER" title in red with flickering effect.
    • Final score / height reached.
    • Two buttons: Retry (returns to Level 1), Main Menu.

    University report — flicker effect:
      The title colour alternates between RED and a darker shade every
      FLICKER_PERIOD frames using integer division of a frame counter.
      This is the same technique used by NES-era games for danger/game-over
      text — cheap, effective, and immediately communicates urgency.
    """

    FLICKER_PERIOD = 18   # frames per colour cycle

    def __init__(self, score: int = 0, high_score: int = 0,
                 retry_state: str = STATE_LEVEL1):
        self.score      = score
        self.high_score = high_score
        self.retry_state = retry_state

        # ---- Fonts ----
        self._font_title = _make_font(FONT_SIZE_LARGE,  bold=True)
        self._font_sub   = _make_font(FONT_SIZE_MEDIUM, bold=False)
        self._font_btn   = _make_font(FONT_SIZE_SMALL,  bold=True)
        self._font_score = _make_font(FONT_SIZE_SMALL,  bold=False)

        # ---- Dark background ----
        self._bg = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        self._bg.fill((5, 0, 15))   # near-black purple

        # ---- Buttons ----
        cx = SCREEN_WIDTH // 2
        self._btn_retry = _Button("RETRY",      cx, 560, self._font_btn,
                                  color_normal=RED,
                                  color_hover=(255, 80, 80))
        self._btn_menu  = _Button("MAIN MENU",  cx, 630, self._font_btn)
        self._focused   = 0
        self._buttons   = [self._btn_retry, self._btn_menu]
        self._buttons[self._focused].selected = True

        # ---- Animation ----
        self._frame: int  = 0
        self.next_state: str | None = None

        # ---- Particles (slow drifting, funereal mood) ----
        self._particles = ParticleSystem()
        self._dust_tick = 0

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> None:
        mouse = pygame.mouse.get_pos()

        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_DOWN, pygame.K_s, pygame.K_RIGHT):
                self._set_focus((self._focused + 1) % len(self._buttons))
            elif event.key in (pygame.K_UP, pygame.K_w, pygame.K_LEFT):
                self._set_focus((self._focused - 1) % len(self._buttons))

        if self._btn_retry.is_clicked(event, mouse):
            self.next_state = self.retry_state

        if self._btn_menu.is_clicked(event, mouse):
            self.next_state = STATE_MENU

    def update(self) -> None:
        self._frame += 1
        for btn in self._buttons:
            btn.update()

        # Slowly emit dim dust particles for atmosphere
        self._dust_tick += 1
        if self._dust_tick >= 20:
            self._dust_tick = 0
            import random
            self._particles.landing_dust(
                (random.randint(0, SCREEN_WIDTH), SCREEN_HEIGHT)
            )
        self._particles.update()

    def draw(self, surface: pygame.Surface) -> None:
        surface.blit(self._bg, (0, 0))
        self._particles.draw(surface)

        # ---- Flickering title ----
        flicker_on = (self._frame // self.FLICKER_PERIOD) % 2 == 0
        title_color = RED if flicker_on else (140, 0, 0)
        _draw_text(surface, "GAME OVER",
                   self._font_title, title_color,
                   SCREEN_WIDTH // 2, 200,
                   shadow=True)

        # ---- Score summary ----
        _draw_text(surface, f"FINAL SCORE:   {self.score:>8}",
                   self._font_score, GOLD,
                   SCREEN_WIDTH // 2, 310)
        _draw_text(surface, f"HIGH SCORE:    {self.high_score:>8}",
                   self._font_score, CYAN,
                   SCREEN_WIDTH // 2, 345)

        new_record = self.score >= self.high_score and self.score > 0
        if new_record:
            pulse_alpha = int(180 + 75 * math.sin(self._frame * 0.1))
            record_surf = self._font_sub.render("NEW HIGH SCORE!", True, GOLD)
            record_surf.set_alpha(pulse_alpha)
            rr = record_surf.get_rect(center=(SCREEN_WIDTH // 2, 395))
            surface.blit(record_surf, rr)

        # ---- Buttons ----
        mouse = pygame.mouse.get_pos()
        for btn in self._buttons:
            btn.draw(surface, mouse)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _set_focus(self, idx: int) -> None:
        self._buttons[self._focused].selected = False
        self._focused = idx
        self._buttons[self._focused].selected = True


# ---------------------------------------------------------------------------
# WIN SCREEN
# ---------------------------------------------------------------------------

class WinScreen:
    """
    Displayed after the players collect the moon crystal in Level 1.

    Elements
    --------
    • "MISSION COMPLETE!" title with a green pulsing glow.
    • Continuous green aura particle system erupting from the centre.
    • Two buttons: Continue to Level 2, Main Menu.

    University report — celebratory particle system:
      ParticleSystem.crystal_aura() is called every frame on update() with
      the screen centre as origin.  Because the aura emitter outputs only 2–4
      particles per call, the system stays lightweight even over the 2–3
      seconds the screen is shown.  The upward drift and sine-wave wobble
      (defined in effects.py) give the particles an organic, magical quality
      that matches the moon-crystal theme.
    """

    def __init__(self, p1_crystals: int = 0, p2_crystals: int = 0):
        self.p1_crystals = p1_crystals
        self.p2_crystals = p2_crystals

        # ---- Fonts ----
        self._font_title = _make_font(FONT_SIZE_LARGE,  bold=True)
        self._font_sub   = _make_font(FONT_SIZE_MEDIUM, bold=False)
        self._font_btn   = _make_font(FONT_SIZE_SMALL,  bold=True)

        # ---- Background ----
        self._bg = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        self._bg.fill((0, 8, 20))

        # ---- Particles ----
        self._particles = ParticleSystem()

        # ---- Victory sound ----
        snd = _load_sound(SFX_VICTORY)
        if snd:
            snd.play()

        # ---- Buttons ----
        cx = SCREEN_WIDTH // 2
        self._btn_menu = _Button("MAIN MENU", cx, 620, self._font_btn)
        self._focused  = 0
        self._buttons  = [self._btn_menu]
        self._buttons[self._focused].selected = True

        # ---- Animation ----
        self._frame: int = 0
        self._pulse: float = 0.0
        self.next_state: str | None = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> None:
        mouse = pygame.mouse.get_pos()

        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_DOWN, pygame.K_s, pygame.K_RIGHT):
                self._set_focus((self._focused + 1) % len(self._buttons))
            elif event.key in (pygame.K_UP, pygame.K_w, pygame.K_LEFT):
                self._set_focus((self._focused - 1) % len(self._buttons))

        if self._btn_menu.is_clicked(event, mouse):
            self.next_state = STATE_MENU

    def update(self) -> None:
        self._frame += 1
        self._pulse += 0.06

        # Continuously emit aura particles from the screen centre
        self._particles.crystal_aura((SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2))
        self._particles.update()

        for btn in self._buttons:
            btn.update()

    def draw(self, surface: pygame.Surface) -> None:
        surface.blit(self._bg, (0, 0))

        # ---- Aura particles (drawn early so text renders above them) ----
        self._particles.draw(surface)

        # ---- Green glow behind the title ----
        glow_r = int(120 + 40 * math.sin(self._pulse))
        glow_surf = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
        glow_alpha = int(60 + 40 * math.sin(self._pulse))
        pygame.draw.circle(glow_surf, (*GREEN, glow_alpha),
                           (glow_r, glow_r), glow_r)
        surface.blit(glow_surf,
                     (SCREEN_WIDTH // 2 - glow_r, 160 - glow_r))

        # ---- Title ----
        _draw_text(surface, "MISSION COMPLETE!",
                   self._font_title, GREEN,
                   SCREEN_WIDTH // 2, 200,
                   shadow=True, shadow_color=(0, 80, 0))

        # ---- Subtitle ----
        _draw_text(surface, "The moon crystal has been recovered.",
                   self._font_sub, WHITE,
                   SCREEN_WIDTH // 2, 270)

        # ---- Crystal tally ----
        total = self.p1_crystals + self.p2_crystals
        _draw_text(surface, f"Crystals collected: {total}",
                   self._font_sub, COLOR_CRYSTAL,
                   SCREEN_WIDTH // 2, 320)

        # ---- Prompt to continue ----
        prompt_alpha = int(160 + 95 * math.sin(self._pulse * 1.4))
        prompt_surf  = self._font_sub.render(
            "Choose another mission from the menu.",
            True, CYAN,
        )
        prompt_surf.set_alpha(prompt_alpha)
        pr = prompt_surf.get_rect(center=(SCREEN_WIDTH // 2, 390))
        surface.blit(prompt_surf, pr)

        # ---- Buttons ----
        mouse = pygame.mouse.get_pos()
        for btn in self._buttons:
            btn.draw(surface, mouse)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _set_focus(self, idx: int) -> None:
        self._buttons[self._focused].selected = False
        self._focused = idx
        self._buttons[self._focused].selected = True
