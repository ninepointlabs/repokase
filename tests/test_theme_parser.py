from pathlib import Path

import pytest

from repokase.theme.colors import Rgba, parse_color
from repokase.theme.parser import resolve

FIXTURES = Path(__file__).parent / "fixtures" / "themes"
STOCK = Path("/usr/share/omarchy/themes")


@pytest.mark.parametrize(
    "text, expected",
    [
        ("#f38d70", Rgba(0xF3, 0x8D, 0x70)),
        ("#FFF", Rgba(255, 255, 255)),
        ("#00000080", Rgba(0, 0, 0, 128 / 255)),
        ("rgba(595959aa)", Rgba(0x59, 0x59, 0x59, 0xAA / 255)),
        ("rgb(33ccff)", Rgba(0x33, 0xCC, 0xFF)),
        ("rgba(33ccffee) rgba(00ff99ee) 45deg", Rgba(0x33, 0xCC, 0xFF, 0xEE / 255)),
        ("rgba(10, 20, 30, 0.5)", Rgba(10, 20, 30, 0.5)),
        ("  #abcdef  ", Rgba(0xAB, 0xCD, 0xEF)),
    ],
)
def test_parse_color_accepts_omarchy_syntaxes(text, expected):
    assert parse_color(text) == expected


@pytest.mark.parametrize("text", ["", "red", "#12", "#gggggg", "rgba(300, 0, 0)", None, 12])
def test_parse_color_rejects_garbage(text):
    assert parse_color(text) is None


def test_hex_uses_qt_argb_order_for_alpha():
    assert Rgba(0x11, 0x22, 0x33, 0.5).hex() == "#80112233"
    assert Rgba(0x11, 0x22, 0x33).hex() == "#112233"


def test_ristretto_maps_palette_roles():
    t = resolve(FIXTURES / "ristretto")
    assert t.source == "omarchy"
    assert t.name == "ristretto"
    assert t.is_dark
    c = t.colors
    assert c["bg"].hex() == "#2c2525"
    assert c["bgSunken"].hex() == "#211b1b"
    assert c["bgInset"].hex() == "#181414"
    assert c["bgRaised"].hex() == "#3d2f2a"
    assert c["fg"].hex() == "#e6d9db"
    assert c["accent"].hex() == "#f38d70"
    assert c["focusRing"].hex() == "#f38d70"  # shell.toml [hyprland] active-border
    assert c["danger"].hex() == "#fd6883"
    assert c["success"].hex() == "#adda78"
    # State fills come from shell.toml [controls] alphas over foreground.
    assert c["hoverFill"] == Rgba(0xE6, 0xD9, 0xDB, 0.08)
    assert c["selectedFill"] == Rgba(0xE6, 0xD9, 0xDB, 0.18)
    assert t.font_sizes["body"] == 12
    assert t.font_sizes["heading"] == 16
    assert t.spacing["control-height"] == 28


def test_text_on_accent_is_readable():
    for name in ("ristretto", "white"):
        c = resolve(FIXTURES / name).colors
        assert c["accent"].contrast(c["accentFg"]) >= 4.5


def test_muted_text_meets_minimum_contrast():
    for name in ("ristretto", "white"):
        c = resolve(FIXTURES / name).colors
        assert c["fgMuted"].contrast(c["bg"]) >= 3.0


def test_light_theme_without_shell_toml_or_orange():
    t = resolve(FIXTURES / "white")
    assert not t.is_dark
    assert t.colors["bg"].hex() == "#ffffff"
    # Monochrome theme: grey "red" is not saturated, so danger falls back to accent
    # rather than a foreign hue.
    assert t.colors["danger"] == t.colors["accent"]
    # Missing orange must not pull in a fallback hue.
    assert all(c.saturation() < 0.25 for c in t.series)
    # No shell.toml: shell defaults apply.
    assert t.colors["hoverFill"].a == pytest.approx(0.08)
    assert t.colors["focusRing"] == t.colors["accent"]


def test_missing_directory_uses_fallback():
    t = resolve(Path("/nonexistent/theme"))
    assert t.source == "fallback"
    assert t.name == "fallback"
    assert t.colors["bg"].hex() == "#1a1b26"


def test_none_uses_fallback():
    assert resolve(None).source == "fallback"


def test_corrupt_colors_toml_falls_back(tmp_path):
    (tmp_path / "colors.toml").write_text("this is = = not toml")
    t = resolve(tmp_path)
    assert t.source == "fallback"


def test_partial_colors_fill_per_key(tmp_path):
    (tmp_path / "colors.toml").write_text('background = "#101010"\nforeground = "#f0f0f0"\n')
    t = resolve(tmp_path)
    assert t.source == "omarchy"
    assert t.colors["bg"].hex() == "#101010"
    assert t.colors["accent"].hex() == "#7aa2f7"  # per-key fallback
    assert t.is_dark  # inferred from luminance when `mode` is absent


def test_theme_name_comes_from_sibling_theme_name_file(tmp_path):
    theme = tmp_path / "theme"
    theme.mkdir()
    (theme / "colors.toml").write_text('background = "#000000"\n')
    (tmp_path / "theme.name").write_text("tokyo-night\n")
    assert resolve(theme).name == "tokyo-night"


def test_font_base_size_and_spacing_scale(tmp_path):
    (tmp_path / "colors.toml").write_text('background = "#000000"\n')
    (tmp_path / "shell.toml").write_text(
        "[font]\nbase-size = 18\nheading = 30\n[spacing]\nscale = 1.0\ncontrol-height = 40\n"
    )
    t = resolve(tmp_path)
    assert t.font_sizes["body"] == 18
    assert t.font_sizes["caption"] == round(18 * 0.833)
    assert t.font_sizes["heading"] == 30  # pinned override
    assert t.spacing["lg"] == 12  # 8 * 18/12, scale-with-font default
    assert t.spacing["control-height"] == 40


def test_shell_reference_values_resolve(tmp_path):
    (tmp_path / "colors.toml").write_text('background = "#000000"\naccent = "#ff0000"\n')
    (tmp_path / "shell.toml").write_text(
        '[hyprland]\nactive-border = "rgba(33ccffee) rgba(00ff99ee) 45deg"\n'
    )
    t = resolve(tmp_path)
    assert t.colors["focusRing"] == Rgba(0x33, 0xCC, 0xFF, 0xEE / 255)


@pytest.mark.skipif(not STOCK.is_dir(), reason="Omarchy stock themes not installed")
def test_every_stock_theme_resolves_readably():
    themes = [d for d in STOCK.iterdir() if (d / "colors.toml").exists()]
    assert themes
    for d in themes:
        t = resolve(d)
        assert t.source == "omarchy", d.name
        c = t.colors
        assert c["fg"].contrast(c["bg"]) >= 3.0, d.name
        assert c["fgMuted"].contrast(c["bg"]) >= 3.0, d.name
        assert c["accent"].contrast(c["accentFg"]) >= 3.0, d.name
