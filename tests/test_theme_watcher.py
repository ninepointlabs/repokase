"""Simulates `omarchy theme set`: rm -rf current/theme; mv next-theme theme; write theme.name."""

import shutil
import time
from pathlib import Path

import pytest

from PySide6.QtCore import QCoreApplication

from repokase.theme.watcher import PathWatcher, omarchy_watch_paths

FIXTURES = Path(__file__).parent / "fixtures" / "themes"


@pytest.fixture(scope="module")
def qapp():
    return QCoreApplication.instance() or QCoreApplication([])


def spin(app, predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


def install(current: Path, fixture: str, name: str) -> None:
    nxt = current / "next-theme"
    shutil.copytree(FIXTURES / fixture, nxt)
    shutil.rmtree(current / "theme", ignore_errors=True)
    nxt.rename(current / "theme")
    (current / "theme.name").write_text(name + "\n")


def test_theme_swap_triggers_single_debounced_reload(qapp, tmp_path):
    current = tmp_path / "current"
    current.mkdir()
    install(current, "ristretto", "ristretto")
    watcher = PathWatcher(
        omarchy_watch_paths(current, tmp_path / "fontconfig", tmp_path), debounce_ms=50
    )
    hits = []
    watcher.changed.connect(lambda: hits.append(1))

    install(current, "white", "white")
    assert spin(qapp, lambda: hits)
    spin(qapp, lambda: False, timeout=0.3)
    assert len(hits) == 1, "burst of fs events should debounce to one reload"

    # Watches must be re-armed on the new theme directory: a second swap fires again.
    assert str(current / "theme" / "colors.toml") in watcher.watched()
    install(current, "ristretto", "ristretto")
    assert spin(qapp, lambda: len(hits) >= 2)


def test_in_place_edit_triggers_reload(qapp, tmp_path):
    current = tmp_path / "current"
    current.mkdir()
    install(current, "ristretto", "ristretto")
    watcher = PathWatcher(omarchy_watch_paths(current, tmp_path / "fc", tmp_path), debounce_ms=30)
    hits = []
    watcher.changed.connect(lambda: hits.append(1))
    colors = current / "theme" / "colors.toml"
    colors.write_text(colors.read_text().replace("#f38d70", "#00ff00"))
    assert spin(qapp, lambda: hits)


def test_fontconfig_created_later_is_picked_up(qapp, tmp_path):
    current = tmp_path / "current"
    current.mkdir()
    install(current, "ristretto", "ristretto")
    fontconfig = tmp_path / "fontconfig"
    watcher = PathWatcher(omarchy_watch_paths(current, fontconfig, tmp_path), debounce_ms=30)
    hits = []
    watcher.changed.connect(lambda: hits.append(1))
    # First `omarchy font set` creates ~/.config/fontconfig/fonts.conf.
    fontconfig.mkdir()
    assert spin(qapp, lambda: hits)
    assert str(fontconfig) in watcher.watched()
    hits.clear()
    (fontconfig / "fonts.conf").write_text("<fontconfig/>")
    assert spin(qapp, lambda: hits)


def test_missing_omarchy_state_does_not_crash(qapp, tmp_path):
    watcher = PathWatcher(omarchy_watch_paths(tmp_path / "nope", tmp_path / "fc", tmp_path))
    assert str(tmp_path) in watcher.watched()


def test_theme_singleton_repaints_on_swap_and_ignores_noise(qapp, tmp_path, monkeypatch):
    from repokase.theme import theme as theme_mod

    monkeypatch.setattr(theme_mod.system, "monospace_family", lambda: "Test Mono")
    monkeypatch.setattr(theme_mod.system, "hyprland_rounding", lambda: 0)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    current = tmp_path / "current"
    current.mkdir()
    install(current, "ristretto", "ristretto")

    t = theme_mod.Theme(current / "theme")
    t._watcher._timer.setInterval(30)
    emitted = []
    t.changed.connect(lambda: emitted.append(t.property("bg").name()))
    assert t.property("bg").name() == "#2c2525"
    assert t.property("fontFamily") == "Test Mono"

    # Staging dir appearing next to the theme is noise: no repaint.
    (current / "next-theme").mkdir()
    spin(qapp, lambda: False, timeout=0.2)
    (current / "next-theme").rmdir()
    spin(qapp, lambda: False, timeout=0.2)
    assert emitted == []

    install(current, "white", "white")
    assert spin(qapp, lambda: emitted)
    assert emitted[-1] == "#ffffff"
    assert t.property("name") == "white"
    assert t.property("isDark") is False
