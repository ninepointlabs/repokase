#!/usr/bin/env bash
# Check a built Repokase AppImage against the Nine Point Labs AppImage
# checklist. Needs Xvfb, xdotool, xprop, desktop-file-validate and
# appstreamcli (packaging/appimage/build-deps.txt). Runs headless.
#
#   smoke-test.sh dist-appimage/repokase-<version>-x86_64.AppImage
set -uo pipefail

APPIMAGE_FILE="$(readlink -f -- "${1:?usage: $0 path/to/repokase-*.AppImage}")"
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
APP_ID=repokase
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
failures=0

pass() { printf 'PASS  %s\n' "$*"; }
fail() { printf 'FAIL  %s\n' "$*"; failures=$((failures + 1)); }
note() { printf 'INFO  %s\n' "$*"; }
section() { printf '\n== %s\n' "$*"; }

# A clean session: empty HOME, no Omarchy, no Hyprland, no keyring, no D-Bus
# session bus, and a PATH without hyprctl or omarchy-* helpers.
clean_env() {
    env -i HOME="$T/home" PATH="${CLEAN_PATH:-/usr/bin:/bin}" LANG=C.UTF-8 \
        XDG_RUNTIME_DIR="$T/run" ${DISPLAY:+DISPLAY="$DISPLAY"} "$@"
}
mkdir -p "$T/home" "$T/run" && chmod 700 "$T/run"

# Lines that mean something is broken, whatever the exit code says.
bad_output() {
    grep -E 'Traceback|Error:|could not (load|find|connect)|Could not (load|find)|cannot open shared|not found|undefined symbol|QML warning|qt\.qpa\.plugin' "$1"
}

section "AppDir contents"
(cd "$T" && "$APPIMAGE_FILE" --appimage-extract >/dev/null) || { fail "--appimage-extract"; exit 1; }
AD="$T/squashfs-root"

for f in "$HERE/../$APP_ID.desktop" "$AD/$APP_ID.desktop" "$AD/usr/share/applications/$APP_ID.desktop"; do
    if out="$(desktop-file-validate "$f" 2>&1)" && [ -z "$out" ]; then
        pass "desktop-file-validate ${f#"$T"/}"
    else
        fail "desktop-file-validate ${f#"$T"/}: $out"
    fi
done
grep -q '^StartupWMClass=repokase$' "$AD/$APP_ID.desktop" && pass "StartupWMClass=repokase" || fail "StartupWMClass"
grep -q '^X-AppImage-Version=' "$AD/$APP_ID.desktop" && pass "$(grep '^X-AppImage-Version=' "$AD/$APP_ID.desktop")" ||
    fail "X-AppImage-Version missing"

metainfo="$AD/usr/share/metainfo/com.ninepointlabs.repokase.metainfo.xml"
if out="$(appstreamcli validate --no-net "$metainfo" 2>&1)"; then
    pass "appstreamcli validate --no-net ($(appstreamcli --version | head -n1))"
else
    fail "appstreamcli validate: $out"
fi
[ -n "$out" ] && printf '      %s\n' "$out"

for size in 16 24 32 48 64 128 256 512; do
    png="$AD/usr/share/icons/hicolor/${size}x${size}/apps/$APP_ID.png"
    if file "$png" 2>/dev/null | grep -q "PNG image data, $size x $size,"; then
        pass "icon ${size}x${size}"
    else
        fail "icon ${size}x${size}: $(file "$png" 2>&1)"
    fi
done
[ -s "$AD/usr/share/icons/hicolor/scalable/apps/$APP_ID.svg" ] && pass "icon scalable SVG" || fail "scalable SVG"
file "$AD/$APP_ID.png" | grep -q 'PNG image data, 256 x 256' && pass "root icon $APP_ID.png" || fail "root icon"
[ -s "$AD/.DirIcon" ] && file -L "$AD/.DirIcon" | grep -q 'PNG image data, 256 x 256' && pass ".DirIcon" || fail ".DirIcon"
for p in platforms/libqxcb.so platforms/libqwayland.so; do
    find "$AD" -path "*/Qt/plugins/$p" | grep -q . && pass "Qt plugin $p" || fail "Qt plugin $p missing"
done

info="$(LC_ALL=C readelf -p .upd_info "$APPIMAGE_FILE" 2>/dev/null | grep -o 'gh-releases-zsync|[^ ]*')"
[ -n "$info" ] && pass "update information: $info" || fail "no embedded update information"

section "Host compatibility (newest symbol versions any bundled ELF needs)"
max_ver() { # prefix
    find "$AD" -type f \( -name '*.so*' -o -perm -u+x \) -exec sh -c 'head -c4 "$1" | grep -q ELF && objdump -T "$1" 2>/dev/null' _ {} \; |
        grep -o "$1[0-9.]*" | sed "s/$1//" | sort -uV | tail -n1
}
note "glibc >= $(max_ver 'GLIBC_') required (Ubuntu 22.04: 2.35, Debian 12: 2.36, Fedora 39: 2.38, openSUSE Leap 15.6: 2.38)"
note "libstdc++ GLIBCXX_$(max_ver 'GLIBCXX_') required (Ubuntu 22.04 provides 3.4.30)"
note "AppDir size $(du -sh "$AD" | cut -f1), AppImage size $(du -h "$APPIMAGE_FILE" | cut -f1)"

# Releases before 0.2.5 have no --self-test; launch them with the
# screenshot hook instead (start, render, grab, quit).
if grep -q -- '--self-test' "$AD"/opt/python*/lib/python*/site-packages/repokase/__main__.py; then
    self_test=1
else
    self_test=0
    note "this Repokase predates --self-test: launch checks use REPOKASE_SCREENSHOT, env checks skipped"
fi
launch() { # name, then env assignments; runs the app once and checks its output
    local name="$1"; shift
    local log="$T/$name.log"
    if [ "$self_test" = 1 ]; then
        clean_env "$@" timeout 60 "$APPIMAGE_FILE" --appimage-extract-and-run --self-test >"$log" 2>&1
    else
        clean_env REPOKASE_SCREENSHOT="$T/$name.png" "$@" timeout 60 "$APPIMAGE_FILE" --appimage-extract-and-run >"$log" 2>&1
    fi
    local rc=$?
    if [ "$self_test" = 0 ] && [ ! -s "$T/$name.png" ]; then
        rc="$rc, no screenshot"
    fi
    if [ "$rc" = 0 ] && ! bad_output "$log" >/dev/null; then
        pass "$name: $(grep '^self-test:' "$log" || echo "started and quit cleanly")"
    else
        fail "$name (exit $rc)"
        sed 's/^/      /' "$log"
    fi
}

section "Headless launch"
launch offscreen QT_QPA_PLATFORM=offscreen

Xvfb :99 -screen 0 1600x1000x24 -nolisten tcp >/dev/null 2>&1 &
xvfb_pid=$!
trap 'kill $xvfb_pid 2>/dev/null; rm -rf "$T"' EXIT
export DISPLAY=:99
for _ in $(seq 50); do xdpyinfo >/dev/null 2>&1 && break; sleep 0.1; done
launch xcb-under-Xvfb QT_QPA_PLATFORM=xcb

section "Window class (X11)"
if [ "$self_test" = 1 ]; then
    clean_env QT_QPA_PLATFORM=xcb REPOKASE_SELF_TEST_DELAY=8000 \
        "$APPIMAGE_FILE" --appimage-extract-and-run --self-test >"$T/wmclass.log" 2>&1 &
else
    clean_env QT_QPA_PLATFORM=xcb REPOKASE_SCREENSHOT="$T/wm.png" REPOKASE_SCREENSHOT_DELAY=8000 \
        "$APPIMAGE_FILE" --appimage-extract-and-run >"$T/wmclass.log" 2>&1 &
fi
app_pid=$!
# Qt also makes 1x1 helper windows with the same title; take the one with a
# WM_CLASS.
wm_class=""
for _ in $(seq 60); do
    for win in $(xdotool search --name '^Repokase$' 2>/dev/null); do
        wm_class="$(xprop -id "$win" WM_CLASS 2>/dev/null | sed -n 's/^WM_CLASS(STRING) = //p')"
        [ -n "$wm_class" ] && break 2
    done
    sleep 0.5
done
if [ -n "$wm_class" ]; then
    note "WM_CLASS = $wm_class"
    case "$wm_class" in
        '"repokase", "repokase"') pass "WM_CLASS matches StartupWMClass=repokase" ;;
        *) fail "WM_CLASS $wm_class does not match StartupWMClass=repokase" ;;
    esac
else
    fail "no Repokase window appeared under Xvfb"
fi
wait $app_pid 2>/dev/null

section "Degrade: no Omarchy, no hyprctl, empty HOME"
if [ -z "$(CLEAN_PATH=/usr/bin:/bin command -v hyprctl)" ]; then
    launch degrade QT_QPA_PLATFORM=xcb
    grep -q 'theme=fallback/' "$T/degrade.log" && pass "theme fell back to the built-in palette" ||
        { [ "$self_test" = 1 ] && fail "theme did not fall back"; }
else
    note "hyprctl is on /usr/bin here; run this on a machine without Hyprland"
fi

section "Programs Repokase starts get a clean environment"
if [ "$self_test" = 0 ]; then
    note "skipped: needs --self-test"
else
    mkdir -p "$T/fakebin"
    cat > "$T/fakebin/xdg-open" <<EOF
#!/bin/sh
env > "$T/child-env.txt"
EOF
    chmod +x "$T/fakebin/xdg-open"
    CLEAN_PATH="$T/fakebin:/usr/bin:/bin" clean_env QT_QPA_PLATFORM=xcb XDG_DATA_DIRS=/host/share \
        REPOKASE_SELF_TEST_URL=https://example.invalid/repokase-self-test \
        timeout 60 "$APPIMAGE_FILE" --appimage-extract-and-run --self-test >"$T/env.log" 2>&1
    for _ in $(seq 30); do [ -s "$T/child-env.txt" ] && break; sleep 0.1; done
    if [ -s "$T/child-env.txt" ]; then
        leaked="$(grep -E '^(APPIMAGE|APPDIR|ARGV0|OWD|REPOKASE_APPIMAGE|PYTHONHOME|PYTHONPATH|LD_LIBRARY_PATH|LD_PRELOAD|QT_PLUGIN_PATH|QML2_IMPORT_PATH|QML_IMPORT_PATH|QT_QPA_PLATFORM_PLUGIN_PATH|SSL_CERT_FILE)=' "$T/child-env.txt")"
        [ -z "$leaked" ] && pass "xdg-open saw no AppImage, Python or Qt variables" ||
            fail "variables leaked to xdg-open: $leaked"
        grep -qx 'XDG_DATA_DIRS=/host/share' "$T/child-env.txt" && pass "xdg-open saw the host XDG_DATA_DIRS" ||
            fail "XDG_DATA_DIRS changed: $(grep XDG_DATA_DIRS "$T/child-env.txt")"
    else
        fail "the app never ran xdg-open"
        sed 's/^/      /' "$T/env.log"
    fi
fi

section "--install-desktop-entry / --remove-desktop-entry"
spaced="$T/My Apps/Repokase \$test.AppImage"
mkdir -p "$T/My Apps" && cp "$APPIMAGE_FILE" "$spaced"
data="$T/xdg-data"
clean_env APPIMAGE_EXTRACT_AND_RUN=1 XDG_DATA_HOME="$data" "$spaced" --install-desktop-entry >"$T/install.log" 2>&1
installed="$data/applications/$APP_ID.desktop"
if [ -f "$installed" ]; then
    pass "desktop file installed"
    if out="$(desktop-file-validate "$installed" 2>&1)" && [ -z "$out" ]; then
        pass "installed desktop file validates"
    else
        fail "installed desktop file: $out"
    fi
    note "$(grep -E '^(Exec|TryExec)=' "$installed" | tr '\n' ' ')"
    expected="Exec=\"$T/My Apps/Repokase \\\\\$test.AppImage\""
    grep -Fxq "$expected" "$installed" &&
        pass "Exec points at the AppImage (quoted, with \$ escaped)" || fail "Exec line wrong"
else
    fail "--install-desktop-entry wrote no desktop file"
    sed 's/^/      /' "$T/install.log"
fi
n_icons="$(find "$data/icons/hicolor" -name "$APP_ID.*" 2>/dev/null | wc -l)"
[ "$n_icons" = 9 ] && pass "9 icons installed" || fail "$n_icons icons installed, expected 9"
clean_env APPIMAGE_EXTRACT_AND_RUN=1 XDG_DATA_HOME="$data" "$spaced" --install-desktop-entry >/dev/null 2>&1 &&
    pass "installing again is fine (idempotent)" || fail "second install failed"
cp "$HERE/../$APP_ID.desktop" "$T/foreign.desktop"
clean_env APPIMAGE_EXTRACT_AND_RUN=1 XDG_DATA_HOME="$data" "$spaced" --remove-desktop-entry >"$T/remove.log" 2>&1
left="$(find "$data" -type f -name "$APP_ID.*" 2>/dev/null)"
[ -z "$left" ] && pass "--remove-desktop-entry removed every file" || fail "left behind: $left"
# A desktop file someone else put there (e.g. by hand) is never removed.
mkdir -p "$data/applications" && cp "$T/foreign.desktop" "$installed"
clean_env APPIMAGE_EXTRACT_AND_RUN=1 XDG_DATA_HOME="$data" "$spaced" --remove-desktop-entry >/dev/null 2>&1
[ -f "$installed" ] && pass "a desktop file it did not create is left alone" || fail "removed a foreign desktop file"
(cd "$T/My Apps" && clean_env XDG_DATA_HOME="$data" "$T/squashfs-root/AppRun" --install-desktop-entry >"$T/noappimage.log" 2>&1)
[ $? -ne 0 ] && grep -q 'only works when you run the .AppImage' "$T/noappimage.log" &&
    pass "extracted copy: friendly refusal" || fail "extracted copy did not refuse"

section "Result"
if [ "$failures" -eq 0 ]; then
    echo "All checks passed."
else
    echo "$failures check(s) failed."
    exit 1
fi
