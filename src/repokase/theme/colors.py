"""Tiny color value type and parsing for Omarchy theme files (no Qt)."""

from __future__ import annotations

import re
from dataclasses import dataclass

_HEX = re.compile(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
_HYPR_HEX = re.compile(r"^rgba?\(([0-9a-fA-F]{6}|[0-9a-fA-F]{8})\)$")
_CSS_RGBA = re.compile(
    r"^rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*(?:,\s*([0-9.]+)\s*)?\)$"
)


@dataclass(frozen=True)
class Rgba:
    r: int
    g: int
    b: int
    a: float = 1.0

    def hex(self) -> str:
        """#RRGGBB, or #AARRGGBB (Qt order) when translucent."""
        rgb = f"{self.r:02x}{self.g:02x}{self.b:02x}"
        if self.a >= 1.0:
            return f"#{rgb}"
        return f"#{round(self.a * 255):02x}{rgb}"

    def with_alpha(self, alpha: float) -> Rgba:
        return Rgba(self.r, self.g, self.b, max(0.0, min(1.0, alpha)))

    def mix(self, other: Rgba, t: float) -> Rgba:
        """Linear blend toward `other` by t (0 = self, 1 = other), opaque."""
        return Rgba(
            round(self.r + (other.r - self.r) * t),
            round(self.g + (other.g - self.g) * t),
            round(self.b + (other.b - self.b) * t),
        )

    def luminance(self) -> float:
        def chan(c: int) -> float:
            s = c / 255
            return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

        return 0.2126 * chan(self.r) + 0.7152 * chan(self.g) + 0.0722 * chan(self.b)

    def contrast(self, other: Rgba) -> float:
        hi, lo = sorted((self.luminance(), other.luminance()), reverse=True)
        return (hi + 0.05) / (lo + 0.05)

    def saturation(self) -> float:
        mx, mn = max(self.r, self.g, self.b), min(self.r, self.g, self.b)
        return 0.0 if mx == 0 else (mx - mn) / mx


def parse_color(value: object) -> Rgba | None:
    """Parse the color syntaxes Omarchy themes use.

    Accepts #rgb, #rrggbb, #rrggbbaa (CSS order), Hyprland rgba(rrggbbaa),
    CSS rgba(r, g, b, a), and Hyprland gradients ("rgba(..) rgba(..) 45deg"),
    of which the first color is used.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    match = _CSS_RGBA.match(text)
    if match:
        r, g, b = (int(match.group(i)) for i in (1, 2, 3))
        if max(r, g, b) > 255:
            return None
        a = float(match.group(4)) if match.group(4) else 1.0
        return Rgba(r, g, b, max(0.0, min(1.0, a)))
    token = text.split()[0]
    match = _HYPR_HEX.match(token)
    if match:
        token = match.group(1)
    match = _HEX.match(token)
    if not match:
        return None
    h = match.group(1)
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    a = int(h[6:8], 16) / 255 if len(h) == 8 else 1.0
    return Rgba(r, g, b, a)
