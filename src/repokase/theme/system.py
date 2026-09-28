"""Desktop values that live outside the theme: font family and corner rounding."""

from __future__ import annotations

import json
import shutil
import subprocess


def _run(cmd: list[str]) -> str | None:
    if not shutil.which(cmd[0]):
        return None
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=1, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout if out.returncode == 0 else None


def monospace_family() -> str:
    """The family `omarchy font set` configured, via fontconfig's monospace alias."""
    out = _run(["fc-match", "-f", "%{family[0]}", "monospace"])
    return out.strip() if out and out.strip() else "monospace"


def hyprland_rounding() -> int:
    """Hyprland's decoration:rounding, which the Omarchy shell mirrors too."""
    out = _run(["hyprctl", "-j", "getoption", "decoration:rounding"])
    if not out:
        return 0
    try:
        return max(0, int(json.loads(out).get("int", 0)))
    except (ValueError, TypeError, AttributeError):
        return 0
