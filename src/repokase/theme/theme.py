"""The Theme singleton exposed to QML. Every color in the UI binds here."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from PySide6.QtCore import Property, QObject, Signal, Slot
from PySide6.QtGui import QColor

from .. import config
from . import system
from .parser import ThemeData, resolve
from .watcher import PathWatcher, omarchy_watch_paths

log = logging.getLogger(__name__)


def current_theme_dir() -> Path:
    override = os.environ.get("REPOKASE_THEME_DIR")
    if override:
        return Path(override)
    return config.state_home() / "omarchy" / "current" / "theme"


def _color_prop(key: str, notify):
    return Property(QColor, lambda self: self._colors[key], notify=notify)


def _font_prop(key: str, notify):
    return Property(int, lambda self: self._data.font_sizes[key], notify=notify)


def _space_prop(key: str, notify):
    return Property(int, lambda self: self._data.spacing[key], notify=notify)


class Theme(QObject):
    # One notify signal for every property: a reload swaps all values and
    # emits once, so QML re-evaluates bindings in a single pass.
    changed = Signal()

    def __init__(self, theme_dir: Path | None = None, watch: bool = True, parent=None):
        super().__init__(parent)
        self._theme_dir = theme_dir or current_theme_dir()
        self._data: ThemeData
        self._colors: dict[str, QColor] = {}
        self._family = "monospace"
        self._radius = 0
        self._load()
        self._watcher = None
        if watch:
            fontconfig = config.config_home() / "fontconfig"
            self._watcher = PathWatcher(
                omarchy_watch_paths(self._theme_dir.parent, fontconfig, config.config_home()),
                parent=self,
            )
            self._watcher.changed.connect(self.reload)

    def _load(self) -> bool:
        """Re-resolve everything; returns False when nothing changed."""
        data = resolve(self._theme_dir)
        family = system.monospace_family()
        radius = system.hyprland_rounding()
        if getattr(self, "_data", None) == data and family == self._family and radius == self._radius:
            return False
        self._data = data
        self._colors = {k: QColor(v.hex()) for k, v in data.colors.items()}
        self._series = [QColor(c.hex()) for c in data.series]
        self._family = family
        self._radius = radius
        log.info("Theme loaded: %s (%s)", data.name, data.source)
        return True

    @Slot()
    def reload(self) -> None:
        # Omarchy touches the state dir several times per switch (next-theme
        # staging, post-set hooks); only repaint when the result differs.
        if self._load():
            self.changed.emit()

    # -- identity
    name = Property(str, lambda self: self._data.name, notify=changed)
    source = Property(str, lambda self: self._data.source, notify=changed)
    isDark = Property(bool, lambda self: self._data.is_dark, notify=changed)

    # -- colors
    bg = _color_prop("bg", changed)
    bgSunken = _color_prop("bgSunken", changed)
    bgInset = _color_prop("bgInset", changed)
    bgRaised = _color_prop("bgRaised", changed)
    fg = _color_prop("fg", changed)
    fgSecondary = _color_prop("fgSecondary", changed)
    fgMuted = _color_prop("fgMuted", changed)
    accent = _color_prop("accent", changed)
    accentFg = _color_prop("accentFg", changed)
    selection = _color_prop("selection", changed)
    normalFill = _color_prop("normalFill", changed)
    hoverFill = _color_prop("hoverFill", changed)
    focusFill = _color_prop("focusFill", changed)
    selectedFill = _color_prop("selectedFill", changed)
    pressedFill = _color_prop("pressedFill", changed)
    border = _color_prop("border", changed)
    borderStrong = _color_prop("borderStrong", changed)
    focusRing = _color_prop("focusRing", changed)
    success = _color_prop("success", changed)
    warning = _color_prop("warning", changed)
    danger = _color_prop("danger", changed)
    info = _color_prop("info", changed)
    scrim = _color_prop("scrim", changed)

    # -- typography
    fontFamily = Property(str, lambda self: self._family, notify=changed)
    fontCaption = _font_prop("caption", changed)
    fontSmall = _font_prop("body-small", changed)
    fontBody = _font_prop("body", changed)
    fontSubtitle = _font_prop("subtitle", changed)
    fontTitle = _font_prop("title", changed)
    fontHeading = _font_prop("heading", changed)
    fontDisplay = _font_prop("display", changed)

    # -- geometry
    spaceXxs = _space_prop("xxs", changed)
    spaceXs = _space_prop("xs", changed)
    spaceSm = _space_prop("sm", changed)
    spaceMd = _space_prop("md", changed)
    spaceLg = _space_prop("lg", changed)
    spaceXl = _space_prop("xl", changed)
    spaceXxl = _space_prop("xxl", changed)
    spaceXxxl = _space_prop("xxxl", changed)
    spaceHuge = _space_prop("huge", changed)
    controlHeight = _space_prop("control-height", changed)
    controlPaddingX = _space_prop("control-padding-x", changed)
    rowPaddingX = _space_prop("row-padding-x", changed)
    panelPadding = _space_prop("panel-padding", changed)
    radius = Property(int, lambda self: self._radius, notify=changed)
    borderWidth = Property(int, lambda self: 1, notify=changed)
    focusWidth = Property(int, lambda self: 2, notify=changed)

    @Slot(QColor, float, result=QColor)
    def tint(self, color: QColor, alpha: float) -> QColor:
        c = QColor(color)
        c.setAlphaF(max(0.0, min(1.0, alpha)))
        return c

    @Slot(int, result=QColor)
    def seriesAt(self, index: int) -> QColor:
        """Theme color by position, for small ordered sets (categories)."""
        if not self._series:
            return self._colors["accent"]
        return self._series[index % len(self._series)]

    @Slot(str, result=QColor)
    def seriesColor(self, key: str) -> QColor:
        """Stable theme color for a label such as a language name."""
        if not self._series:
            return self._colors["accent"]
        h = 0
        for ch in key:
            h = (h * 31 + ord(ch)) & 0xFFFFFFFF
        return self._series[h % len(self._series)]
