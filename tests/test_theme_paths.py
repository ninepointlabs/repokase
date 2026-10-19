"""Where the Omarchy theme is looked for, and the off-Omarchy fallback."""

from repokase.theme import system, theme


def test_prefers_state_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("REPOKASE_THEME_DIR", raising=False)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    (tmp_path / "state/omarchy/current/theme").mkdir(parents=True)
    (tmp_path / "config/omarchy/current/theme").mkdir(parents=True)
    assert theme.current_theme_dir() == tmp_path / "state/omarchy/current/theme"


def test_falls_back_to_legacy_config_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("REPOKASE_THEME_DIR", raising=False)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    (tmp_path / "config/omarchy/current/theme").mkdir(parents=True)
    assert theme.current_theme_dir() == tmp_path / "config/omarchy/current/theme"


def test_no_omarchy_at_all_keeps_the_standard_path(tmp_path, monkeypatch):
    monkeypatch.delenv("REPOKASE_THEME_DIR", raising=False)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    assert theme.current_theme_dir() == tmp_path / "state/omarchy/current/theme"


def test_no_session_bus_means_no_portal_preference(monkeypatch):
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", "unix:path=/nonexistent/bus")
    assert system.portal_color_scheme() is None


def test_no_hyprctl_means_square_corners(monkeypatch):
    monkeypatch.setattr(system.shutil, "which", lambda _cmd: None)
    assert system.hyprland_rounding() == 0
