"""AppRun --install-desktop-entry / --remove-desktop-entry against a fake AppDir."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APPRUN = ROOT / "packaging" / "appimage" / "AppRun"
ICONS = [
    "16x16/apps/repokase.png", "24x24/apps/repokase.png", "32x32/apps/repokase.png",
    "48x48/apps/repokase.png", "64x64/apps/repokase.png", "128x128/apps/repokase.png",
    "256x256/apps/repokase.png", "512x512/apps/repokase.png", "scalable/apps/repokase.svg",
]

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")


@pytest.fixture
def env(tmp_path):
    appdir = tmp_path / "AppDir"
    appdir.mkdir()
    shutil.copy(ROOT / "packaging" / "repokase.desktop", appdir / "repokase.desktop")
    for rel in ICONS:
        icon = appdir / "usr/share/icons/hicolor" / rel
        icon.parent.mkdir(parents=True, exist_ok=True)
        icon.write_bytes(b"bundled " + rel.encode())
    data = tmp_path / "data"

    def run(*args):
        result = subprocess.run(
            ["bash", str(APPRUN), *args],
            env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "APPDIR": str(appdir),
                 "APPIMAGE": str(tmp_path / "Repokase.AppImage"), "XDG_DATA_HOME": str(data)},
            capture_output=True, text=True,
        )
        return result.returncode, result.stdout + result.stderr

    return run, data / "applications" / "repokase.desktop", data / "icons" / "hicolor"


def test_install_then_remove_leaves_nothing(env):
    run, desktop, icons = env
    assert run("--install-desktop-entry")[0] == 0
    assert desktop.is_file()
    assert all((icons / rel).is_file() for rel in ICONS)
    assert run("--install-desktop-entry")[0] == 0  # again: still fine
    code, out = run("--remove-desktop-entry")
    assert code == 0
    assert not desktop.exists()
    assert not list(icons.rglob("repokase.*"))


def test_remove_without_an_entry_deletes_no_icons(env):
    # QA L1: someone else's icon, no Repokase desktop entry installed.
    run, desktop, icons = env
    mine = icons / "256x256/apps/repokase.png"
    mine.parent.mkdir(parents=True)
    mine.write_bytes(b"my own icon")
    code, out = run("--remove-desktop-entry")
    assert code == 0
    assert mine.read_bytes() == b"my own icon"
    assert "Nothing was removed" in out


def test_remove_next_to_a_foreign_desktop_file_deletes_nothing(env):
    run, desktop, icons = env
    desktop.parent.mkdir(parents=True)
    desktop.write_text("[Desktop Entry]\nName=Mine\n")
    mine = icons / "scalable/apps/repokase.svg"
    mine.parent.mkdir(parents=True)
    mine.write_text("<svg/>")
    code, out = run("--remove-desktop-entry")
    assert code == 0
    assert desktop.read_text() == "[Desktop Entry]\nName=Mine\n"
    assert mine.read_text() == "<svg/>"
    assert "Left" in out


def test_install_keeps_existing_icons_and_remove_leaves_them(env):
    run, desktop, icons = env
    mine = icons / "256x256/apps/repokase.png"
    mine.parent.mkdir(parents=True)
    mine.write_bytes(b"my own icon")
    code, out = run("--install-desktop-entry")
    assert code == 0
    assert mine.read_bytes() == b"my own icon"
    assert f"Left {mine} alone" in out
    run("--install-desktop-entry")  # a reinstall must not adopt it either
    run("--remove-desktop-entry")
    assert mine.read_bytes() == b"my own icon"
    assert not desktop.exists()
    assert list(icons.rglob("repokase.*")) == [mine]


def test_install_refuses_to_overwrite_a_foreign_desktop_file(env):
    run, desktop, icons = env
    desktop.parent.mkdir(parents=True)
    desktop.write_text("[Desktop Entry]\nName=Mine\n")
    code, out = run("--install-desktop-entry")
    assert code != 0
    assert desktop.read_text() == "[Desktop Entry]\nName=Mine\n"
    assert not icons.exists()


def test_remove_an_entry_from_0_2_5_still_removes_its_icons(env):
    # 0.2.5 wrote the marker but no icon list; it installed all nine.
    run, desktop, icons = env
    run("--install-desktop-entry")
    text = "".join(l for l in desktop.read_text().splitlines(True) if not l.startswith("X-Repokase-Icons="))
    desktop.write_text(text)
    run("--remove-desktop-entry")
    assert not desktop.exists()
    assert not list(icons.rglob("repokase.*"))


def test_installed_desktop_file_validates(env):
    if shutil.which("desktop-file-validate") is None:
        pytest.skip("desktop-file-validate not installed")
    run, desktop, icons = env
    run("--install-desktop-entry")
    result = subprocess.run(["desktop-file-validate", str(desktop)], capture_output=True, text=True)
    assert result.returncode == 0 and not result.stdout.strip(), result.stdout
