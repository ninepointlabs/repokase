"""Keep AppImage variables away from the programs Repokase starts.

The AppImage runtime sets APPIMAGE, APPDIR, ARGV0 and OWD, and our launcher
(packaging/appimage/AppRun) marks the process with REPOKASE_APPIMAGE=1. It
exports nothing else: the bundled Python and Qt find their libraries through
RUNPATH. Once Qt is up none of these are needed, and children such as
xdg-open or a browser (some apps act on APPIMAGE themselves, e.g. to update)
must not see them.

Outside the Repokase AppImage this does nothing.
"""

from __future__ import annotations

import os
from collections.abc import MutableMapping

MARKER = "REPOKASE_APPIMAGE"
RUNTIME_VARS = ("APPIMAGE", "APPDIR", "ARGV0", "OWD")


def restore(environ: MutableMapping[str, str] | None = None) -> None:
    env = os.environ if environ is None else environ
    if env.pop(MARKER, None) is None:
        return
    for name in RUNTIME_VARS:
        env.pop(name, None)
