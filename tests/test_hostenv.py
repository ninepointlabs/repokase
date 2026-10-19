"""AppImage runtime variables never reach the programs Repokase starts."""

from repokase import hostenv


def test_outside_the_appimage_nothing_changes():
    env = {"APPIMAGE": "/other/Thing.AppImage", "APPDIR": "/tmp/.mount_y"}
    hostenv.restore(env)
    assert env == {"APPIMAGE": "/other/Thing.AppImage", "APPDIR": "/tmp/.mount_y"}


def test_drops_runtime_vars_inside_the_appimage():
    env = {
        "REPOKASE_APPIMAGE": "1",
        "APPIMAGE": "/home/me/Repokase.AppImage",
        "APPDIR": "/tmp/.mount_x",
        "ARGV0": "./Repokase.AppImage",
        "OWD": "/home/me",
        "PATH": "/usr/bin",
        "XDG_DATA_DIRS": "/usr/local/share:/usr/share",
    }
    hostenv.restore(env)
    assert env == {"PATH": "/usr/bin", "XDG_DATA_DIRS": "/usr/local/share:/usr/share"}
