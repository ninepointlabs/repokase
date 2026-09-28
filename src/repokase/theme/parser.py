"""Resolve an Omarchy theme directory into Repokase UI roles (no Qt).

Omarchy keeps the active, fully merged theme in
~/.local/state/omarchy/current/theme/. `colors.toml` holds the palette and
the generated `shell.toml` holds the shell's control-state alphas, spacing
scale and font base size. Everything here degrades key by key to a built-in
fallback so a partial or missing theme still yields a usable UI.
"""

from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .colors import Rgba, parse_color

log = logging.getLogger(__name__)

# Tokyo Night, used when no Omarchy theme can be read.
FALLBACK_COLORS: dict[str, str] = {
    "accent": "#7aa2f7",
    "selection": "#292e42",
    "muted": "#565f89",
    "background": "#1a1b26",
    "dark_background": "#13141c",
    "darker_background": "#0e0e14",
    "lighter_background": "#24283b",
    "foreground": "#a9b1d6",
    "red": "#f7768e",
    "yellow": "#e0af68",
    "orange": "#eb927b",
    "green": "#9ece6a",
    "cyan": "#449dab",
    "blue": "#7aa2f7",
    "magenta": "#ad8ee6",
    "bright_red": "#ff7a93",
    "bright_yellow": "#ff9e64",
    "bright_green": "#b9f27c",
    "bright_cyan": "#0db9d7",
    "bright_blue": "#7da6ff",
    "bright_magenta": "#bb9af7",
}

# Defaults mirror /usr/share/omarchy/shell/Commons/Style.qml.
FALLBACK_CONTROLS: dict[str, float] = {
    "normal-fill-alpha": 0.04,
    "normal-border-alpha": 0.4,
    "hover-cursor-fill-alpha": 0.08,
    "hover-cursor-border-alpha": 0.25,
    "focus-fill-alpha": 0.08,
    "selected-fill-alpha": 0.18,
    "pressed-fill-alpha": 0.22,
    "selection-fill-alpha": 0.35,
}

FONT_SCALE: dict[str, float] = {
    "caption": 0.833,
    "body-small": 0.917,
    "body": 1.0,
    "subtitle": 1.083,
    "title": 1.167,
    "heading": 1.333,
    "display": 2.0,
}

SPACING_BASE: dict[str, int] = {
    "xxs": 2,
    "xs": 3,
    "sm": 4,
    "md": 6,
    "lg": 8,
    "xl": 10,
    "xxl": 12,
    "xxxl": 14,
    "huge": 18,
    "control-height": 28,
    "control-padding-x": 10,
    "row-padding-x": 12,
    "panel-padding": 18,
}

ANSI_KEYS = ("red", "yellow", "green", "cyan", "blue", "magenta", "orange")

# Minimum contrast for muted text against the window background.
MUTED_MIN_CONTRAST = 3.0


@dataclass
class ThemeData:
    name: str
    source: str  # "omarchy" or "fallback"
    is_dark: bool
    colors: dict[str, Rgba]
    font_sizes: dict[str, int]
    spacing: dict[str, int]
    series: list[Rgba] = field(default_factory=list)


def _read_toml(path: Path) -> dict:
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except FileNotFoundError:
        return {}
    except (OSError, tomllib.TOMLDecodeError) as exc:
        log.warning("Could not parse %s: %s", path, exc)
        return {}


def _num(value: object, fallback: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return fallback
    return float(value)


def _pick(raw: dict, key: str) -> Rgba:
    return parse_color(raw.get(key)) or parse_color(FALLBACK_COLORS[key])


def _shell_color(shell: dict, section: str, key: str) -> Rgba | None:
    value = shell.get(section, {}).get(key)
    # shell.toml lets values reference other sections, e.g. "hyprland.active-border".
    if isinstance(value, str) and "." in value and not value.lstrip().startswith(("#", "rgb")):
        ref_section, _, ref_key = value.partition(".")
        value = shell.get(ref_section, {}).get(ref_key)
    return parse_color(value)


def _first_saturated(candidates: list[Rgba], fallback: Rgba) -> Rgba:
    for c in candidates:
        if c.saturation() >= 0.25:
            return c
    return fallback


def resolve(theme_dir: Path | None) -> ThemeData:
    colors_raw: dict = {}
    shell: dict = {}
    name = "fallback"
    if theme_dir is not None and theme_dir.is_dir():
        colors_raw = _read_toml(theme_dir / "colors.toml")
        shell = _read_toml(theme_dir / "shell.toml")
        name_file = theme_dir.parent / "theme.name"
        try:
            name = name_file.read_text().strip() or theme_dir.name
        except OSError:
            name = theme_dir.name
    source = "omarchy" if colors_raw else "fallback"
    if not colors_raw:
        name = "fallback"

    bg = _pick(colors_raw, "background")
    fg = _pick(colors_raw, "foreground")
    mode = colors_raw.get("mode")
    is_dark = mode != "light" if mode in ("light", "dark") else bg.luminance() < 0.4

    accent = _pick(colors_raw, "accent")
    muted = _pick(colors_raw, "muted")
    t = 0.0
    while muted.contrast(bg) < MUTED_MIN_CONTRAST and t < 1.0:
        t += 0.1
        muted = _pick(colors_raw, "muted").mix(fg, t)

    controls = {k: _num(shell.get("controls", {}).get(k), v) for k, v in FALLBACK_CONTROLS.items()}
    focus_ring = _shell_color(shell, "hyprland", "active-border") or accent

    # A real theme missing a hue (e.g. `white` has no orange) gets its accent,
    # not a foreign fallback hue.
    ansi = {
        k: (parse_color(colors_raw.get(k)) or accent) if colors_raw else _pick(colors_raw, k)
        for k in ANSI_KEYS
    }
    bright = {k: parse_color(colors_raw.get(f"bright_{k}")) for k in ANSI_KEYS}

    def semantic(key: str) -> Rgba:
        return _first_saturated([c for c in (ansi[key], bright[key]) if c], accent)

    # Prefer the theme's own colors for text on accent; pure black/white only
    # when neither reads well.
    accent_fg = next(
        (c for c in (bg, fg) if accent.contrast(c) >= 4.5),
        max((bg, fg, Rgba(0, 0, 0), Rgba(255, 255, 255)), key=accent.contrast),
    )

    colors = {
        "bg": bg,
        "bgSunken": _pick(colors_raw, "dark_background"),
        "bgInset": _pick(colors_raw, "darker_background"),
        "bgRaised": _pick(colors_raw, "lighter_background"),
        "fg": fg,
        "fgSecondary": fg.mix(bg, 0.25),
        "fgMuted": muted,
        "accent": accent,
        "accentFg": accent_fg,
        "selection": _pick(colors_raw, "selection"),
        "normalFill": fg.with_alpha(controls["normal-fill-alpha"]),
        "hoverFill": fg.with_alpha(controls["hover-cursor-fill-alpha"]),
        "focusFill": fg.with_alpha(controls["focus-fill-alpha"]),
        "selectedFill": fg.with_alpha(controls["selected-fill-alpha"]),
        "pressedFill": fg.with_alpha(controls["pressed-fill-alpha"]),
        "border": fg.with_alpha(controls["hover-cursor-border-alpha"]),
        "borderStrong": fg.with_alpha(controls["normal-border-alpha"]),
        "focusRing": focus_ring,
        "success": semantic("green"),
        "warning": semantic("yellow"),
        "danger": semantic("red"),
        "info": semantic("cyan"),
        "scrim": bg.with_alpha(0.6),
    }

    base_size = int(_num(shell.get("font", {}).get("base-size"), 12)) or 12
    base_size = max(1, base_size)
    font_overrides = shell.get("font", {})
    font_sizes = {}
    for key, mult in FONT_SCALE.items():
        override = font_overrides.get(key)
        font_sizes[key] = (
            round(override) if isinstance(override, (int, float)) and override > 0
            else max(1, round(base_size * mult))
        )

    spacing_cfg = shell.get("spacing", {})
    scale = _num(spacing_cfg.get("scale"), 1.0)
    if scale < 0:
        scale = 1.0
    if spacing_cfg.get("scale-with-font", True) is not False:
        scale *= base_size / 12
    spacing = {}
    for key, px in SPACING_BASE.items():
        override = spacing_cfg.get(key)
        if isinstance(override, (int, float)) and not isinstance(override, bool) and override >= 0:
            spacing[key] = round(override)
        else:
            spacing[key] = max(1, round(px * scale))

    series = [ansi[k] for k in ANSI_KEYS] + [c for c in bright.values() if c]

    return ThemeData(
        name=name,
        source=source,
        is_dark=is_dark,
        colors=colors,
        font_sizes=font_sizes,
        spacing=spacing,
        series=series,
    )
