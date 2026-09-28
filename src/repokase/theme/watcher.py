"""Watch the active Omarchy theme and fontconfig for changes.

`omarchy theme set` replaces ~/.local/state/omarchy/current/theme wholesale
(rm -rf, then mv from next-theme) and writes theme.name last, so watching
files inside the theme is not enough: those watches die with the old
directory. We watch the parent directory plus whichever files exist right
now, debounce the burst of events, and re-arm after every change.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QObject, QTimer, Signal


class PathWatcher(QObject):
    changed = Signal()

    def __init__(self, paths_fn, debounce_ms: int = 150, parent: QObject | None = None):
        """paths_fn returns the paths to watch; re-evaluated on every change."""
        super().__init__(parent)
        self._paths_fn = paths_fn
        self._watcher = QFileSystemWatcher(self)
        self._watcher.fileChanged.connect(self._poke)
        self._watcher.directoryChanged.connect(self._poke)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(debounce_ms)
        self._timer.timeout.connect(self._fire)
        self._arm()

    def watched(self) -> list[str]:
        return self._watcher.files() + self._watcher.directories()

    def _arm(self) -> None:
        current = set(self.watched())
        wanted = {str(p) for p in self._paths_fn() if Path(p).exists()}
        stale = current - wanted
        if stale:
            self._watcher.removePaths(list(stale))
        fresh = wanted - current
        if fresh:
            self._watcher.addPaths(sorted(fresh))

    def _poke(self, _path: str) -> None:
        self._timer.start()

    def _fire(self) -> None:
        # Deleted-and-recreated files silently drop out of QFileSystemWatcher,
        # so always rebuild the watch set before notifying.
        for path in self.watched():
            if not Path(path).exists():
                self._watcher.removePath(path)
        self._arm()
        self.changed.emit()


def omarchy_watch_paths(current_dir: Path, fontconfig_dir: Path, config_home: Path):
    def paths() -> list[Path]:
        theme = current_dir / "theme"
        return [
            current_dir,
            current_dir / "theme.name",
            theme,
            theme / "colors.toml",
            theme / "shell.toml",
            # fonts.conf may not exist until the first `omarchy font set`.
            fontconfig_dir if fontconfig_dir.exists() else config_home,
            fontconfig_dir / "fonts.conf",
        ]

    return paths
