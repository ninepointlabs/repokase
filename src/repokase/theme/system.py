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


def portal_color_scheme() -> str | None:
    """The freedesktop appearance portal's color scheme: "dark", "light" or None.

    Only consulted when there is no Omarchy theme (GNOME, KDE and others).
    None means no preference, no session bus or no portal.
    """
    try:
        from jeepney import DBusAddress, new_method_call
        from jeepney.io.blocking import open_dbus_connection
    except ImportError:
        return None
    portal = DBusAddress(
        "/org/freedesktop/portal/desktop",
        bus_name="org.freedesktop.portal.Desktop",
        interface="org.freedesktop.portal.Settings",
    )
    msg = new_method_call(portal, "ReadOne", "ss", ("org.freedesktop.appearance", "color-scheme"))
    try:
        with open_dbus_connection(bus="SESSION") as conn:
            reply = conn.send_and_get_reply(msg, timeout=1)
        value = reply.body[0]
        # ReadOne returns the value as a variant: (signature, value).
        if isinstance(value, tuple):
            value = value[1]
    except Exception:  # no bus, no portal, timeout, old portal without ReadOne
        return None
    return {1: "dark", 2: "light"}.get(value)
