#!/usr/bin/env bash
# Build repokase-<version>-x86_64.AppImage (+ .zsync and .sha256).
#
# Meant for Ubuntu 22.04 (glibc 2.35), the oldest base the bundled PySide6
# wheels (manylinux_2_34) allow: CI runs it there directly, and
# packaging/appimage/docker-build.sh runs it in an ubuntu:22.04 container.
#
#   build.sh [--app-src DIR] [--out DIR]
#
# --app-src  source tree to package (default: this checkout). CI passes a
#            checkout of the release tag, so a release can be backfilled
#            with the current packaging.
# --out      where the AppImage goes (default: dist-appimage/)
#
# Recipe: relocatable CPython from niess/python-appimage, then the app wheel
# and hash-pinned dependencies (requirements.txt) with pip --no-deps, unused
# Qt pruned, the few host libraries Qt's xcb/wayland plugins need copied in
# (everything on the AppImage excludelist stays on the host), appimagetool.
# Every download is pinned by SHA-256.
set -euo pipefail

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd -- "$HERE/../.." && pwd)"
APP_SRC="$REPO"
OUT="$REPO/dist-appimage"
while [ $# -gt 0 ]; do
    case "$1" in
        --app-src) APP_SRC="$(cd -- "$2" && pwd)"; shift 2 ;;
        --out) OUT="$2"; shift 2 ;;
        *) echo "usage: $0 [--app-src DIR] [--out DIR]" >&2; exit 2 ;;
    esac
done
mkdir -p "$OUT" && OUT="$(cd -- "$OUT" && pwd)"
WORK="${WORK:-$REPO/build/appimage}"
TOOLS="$WORK/tools"
APPDIR="$WORK/AppDir"
APP_ID=repokase
PYVER=3.12

# --- pinned tools -------------------------------------------------------------
# python-appimage republishes its rolling "python3.12" release; when this exact
# file is replaced upstream the hash check fails loudly. Bump both together.
PYTHON_URL="https://github.com/niess/python-appimage/releases/download/python3.12/python3.12.15-cp312-cp312-manylinux_2_28_x86_64.AppImage"
PYTHON_SHA=929ce69b45955bfc74af81fd65a65c3ad240593c99b3574466a94ebf0f987ebf
APPIMAGETOOL_URL="https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage"
APPIMAGETOOL_SHA=ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0
# appimagetool would otherwise download the latest runtime at build time.
RUNTIME_URL="https://github.com/AppImage/type2-runtime/releases/download/20251108/runtime-x86_64"
RUNTIME_SHA=2fca8b443c92510f1483a883f60061ad09b46b978b2631c807cd873a47ec260d
EXCLUDELIST_URL="https://raw.githubusercontent.com/AppImageCommunity/pkg2appimage/15a64c20dc23a0154622ba25829364323903b6b5/excludelist"
EXCLUDELIST_SHA=50db0f894f34b169c47a5cbc0c17dbab61e9edebca5bc8269a1e6ac1bf4bdad9

UPDATE_INFO="gh-releases-zsync|ninepointlabs|repokase|latest|repokase-*x86_64.AppImage.zsync"

log() { printf '\n==> %s\n' "$*"; }

fetch() { # url sha256 dest
    local url="$1" sha="$2" dest="$3"
    if [ -f "$dest" ] && echo "$sha  $dest" | sha256sum -c --quiet - 2>/dev/null; then
        return
    fi
    curl -fsSL --retry 3 -o "$dest.part" "$url"
    if ! echo "$sha  $dest.part" | sha256sum -c --quiet -; then
        echo "Checksum mismatch for $url" >&2
        exit 1
    fi
    mv "$dest.part" "$dest"
}

version="$(sed -n 's/^version = "\(.*\)"$/\1/p' "$APP_SRC/pyproject.toml" | head -n1)"
[ -n "$version" ] || { echo "No version in $APP_SRC/pyproject.toml" >&2; exit 1; }
log "Repokase $version from $APP_SRC"

mkdir -p "$TOOLS"
fetch "$PYTHON_URL" "$PYTHON_SHA" "$TOOLS/python.AppImage"
fetch "$APPIMAGETOOL_URL" "$APPIMAGETOOL_SHA" "$TOOLS/appimagetool.AppImage"
fetch "$RUNTIME_URL" "$RUNTIME_SHA" "$TOOLS/runtime-x86_64"
fetch "$EXCLUDELIST_URL" "$EXCLUDELIST_SHA" "$TOOLS/excludelist"
chmod +x "$TOOLS/python.AppImage" "$TOOLS/appimagetool.AppImage"

# --- Python -------------------------------------------------------------------
log "Relocatable Python $PYVER"
rm -rf "$APPDIR" "$WORK/squashfs-root"
(cd "$WORK" && "$TOOLS/python.AppImage" --appimage-extract >/dev/null)
mv "$WORK/squashfs-root" "$APPDIR"
PY="$APPDIR/opt/python$PYVER/bin/python$PYVER"
# Their launcher, desktop entry, icons and Tcl/Tk go; we only keep the
# interpreter, its stdlib and the libraries it links.
rm -rf "${APPDIR:?}"/AppRun "${APPDIR:?}"/.DirIcon "${APPDIR:?}"/*.desktop "${APPDIR:?}"/*.png \
    "${APPDIR:?}"/usr/bin "${APPDIR:?}"/usr/share "${APPDIR:?}"/opt/_internal \
    "$APPDIR/opt/python$PYVER/include" \
    "$APPDIR"/usr/lib/libtcl* "$APPDIR"/usr/lib/libtk* "$APPDIR"/usr/lib/libX*
STDLIB="$APPDIR/opt/python$PYVER/lib/python$PYVER"
rm -rf "$STDLIB"/{tkinter,idlelib,turtledemo,test,ensurepip,lib2to3} \
    "$STDLIB"/turtle.py "$STDLIB"/lib-dynload/_tkinter*.so

# --- app and dependencies -----------------------------------------------------
log "Repokase wheel and pinned dependencies"
export PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_INPUT=1
rm -rf "$WORK/src" "$WORK/wheel" "$WORK/build-deps"
mkdir -p "$WORK/src"
cp -r "$APP_SRC/src" "$APP_SRC/pyproject.toml" "$APP_SRC/README.md" "$APP_SRC/LICENSE" "$WORK/src/"
"$PY" -I -m pip install -q --no-deps --require-hashes --only-binary=:all: \
    --target "$WORK/build-deps" -r "$HERE/build-requirements.txt"
PYTHONPATH="$WORK/build-deps" "$PY" -s -m pip wheel -q --no-deps --no-build-isolation \
    -w "$WORK/wheel" "$WORK/src"
"$PY" -I -m pip install -q --no-deps --require-hashes --only-binary=:all: --no-warn-script-location \
    -r "$HERE/requirements.txt"
"$PY" -I -m pip install -q --no-deps --no-warn-script-location "$WORK"/wheel/repokase-*.whl
"$PY" -I -m pip uninstall -q -y pip
SP="$("$PY" -I -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
# Console scripts pip wrote carry this machine's absolute path; AppRun starts
# the app through usr/bin/repokase instead.
find "$APPDIR/opt/python$PYVER/bin" -mindepth 1 ! -name "python$PYVER" ! -name python3 ! -name python -delete

# --- prune Qt -----------------------------------------------------------------
# Repokase imports QtCore, QtGui, QtQml and QtQuick from Python (qasync also
# imports QtWidgets), and only
# QtQuick, QtQuick.Layouts, QtQuick.Templates and QtQuick.Window from QML
# (every control is a custom Rk* template). --self-test fails on any QML
# import error, so CI catches anything pruned here that is still needed.
log "Pruning unused Qt"
QT="$SP/PySide6/Qt"
keep_py="QtCore QtGui QtQml QtQuick QtWidgets"
# shiboken imports the binding of every Qt library a kept binding links
# (QtQml needs QtNetwork), so keep those too.
for _ in 1 2 3; do
    for name in $keep_py; do
        for dep in $(readelf -d "$SP/PySide6/$name.abi3.so" | sed -n 's/.*(NEEDED).*\[libQt6\([A-Za-z]*\)\.so.*/\1/p'); do
            [ -e "$SP/PySide6/Qt$dep.abi3.so" ] && case " $keep_py " in *" Qt$dep "*) ;; *) keep_py="$keep_py Qt$dep" ;; esac
        done
    done
done
echo "  Python bindings kept: $keep_py"
for mod in "$SP"/PySide6/Qt*.abi3.so; do
    name="$(basename "$mod" .abi3.so)"
    case " $keep_py " in *" $name "*) ;; *) rm -f "$mod" "$SP/PySide6/$name.pyi" ;; esac
done
# Developer tools (designer, linguist, qml tooling) and build-time files.
find "$SP/PySide6" -maxdepth 1 -type f -perm -u+x ! -name '*.so*' -delete
rm -rf "$SP"/PySide6/{scripts,examples,include,typesystems,glue,doc} \
    "$SP"/shiboken6/{include,docs} "$SP"/shiboken6_generator \
    "$QT"/{libexec,translations,metatypes,modules,mkspecs,resources} \
    "$QT"/lib/cmake "$QT"/lib/pkgconfig "$QT"/lib/*.prl "$QT"/lib/objects-*
# QML: QtQml (base, models, worker script) and the four QtQuick modules used.
rm -rf "$QT"/qml/{Qt,QtCore,QtNetwork,QtWayland,QtTest} \
    "$QT"/qml/QtQml/{StateMachine,XmlListModel}
find "$QT/qml/QtQuick" -mindepth 1 -maxdepth 1 ! -name qmldir ! -name plugins.qmltypes \
    ! -name 'libqtquick2plugin.so' ! -name Layouts ! -name Templates ! -name Window -exec rm -rf {} +
# Plugins: xcb and wayland (plus offscreen/minimal for tests), their GL and
# shell integrations, input methods, image formats, TLS for avatar images.
# The GTK3 theme would load the host's GTK against our libraries; Qt uses the
# xdg-desktop-portal theme instead.
rm -rf "$QT"/plugins/{egldeviceintegrations,generic,networkinformation,vectorimageformats,wayland-graphics-integration-server,designer,sqldrivers,printsupport,qmltooling,qmllint} \
    "$QT"/plugins/platformthemes/libqgtk3.so \
    "$QT"/plugins/platforminputcontexts/libqtvirtualkeyboardplugin.so \
    "$QT"/plugins/imageformats/{libqpdf.so,libqicns.so,libqtiff.so,libqtga.so,libqwbmp.so} \
    "$QT"/plugins/platforms/{libqeglfs.so,libqlinuxfb.so,libqminimalegl.so,libqvkkhrdisplay.so,libqvnc.so}
find "$APPDIR" -name __pycache__ -type d -prune -exec rm -rf {} +

# Keep only the Qt libraries something left over still links (transitively).
qt_needed() { # files... -> sonames of the libQt6 libraries they need
    local f
    for f in "$@"; do
        readelf -d "$f" 2>/dev/null | sed -n 's/.*(NEEDED).*\[\(libQt6[^]]*\)\]/\1/p'
    done
}
mapfile -t roots < <(find "$SP/PySide6" "$SP/shiboken6" -type f -name '*.so*' ! -path "$QT/lib/*")
declare -A keep_qt=()
mapfile -t queue < <(qt_needed "${roots[@]}" | sort -u)
while [ ${#queue[@]} -gt 0 ]; do
    lib="${queue[0]}"; queue=("${queue[@]:1}")
    [ -n "${keep_qt[$lib]:-}" ] && continue
    keep_qt[$lib]=1
    [ -e "$QT/lib/$lib" ] && mapfile -t -O "${#queue[@]}" queue < <(qt_needed "$QT/lib/$lib")
done
for lib in "$QT"/lib/libQt6*.so*; do
    [ -n "${keep_qt[$(basename "$lib")]:-}" ] || rm -f "$lib"
done

# --- host libraries Qt needs that most distros lack -----------------------------
log "Bundling host libraries"
mapfile -t EXCLUDED < <(sed -e 's/#.*//' -e 's/[[:space:]]//g' "$TOOLS/excludelist" | grep -v '^$')
is_excluded() {
    local x
    for x in "${EXCLUDED[@]}"; do [ "$x" = "$1" ] && return 0; done
    return 1
}
elfs() {
    local f
    find "$APPDIR" -type f \( -name '*.so' -o -name '*.so.*' -o -perm -u+x \) -print0 |
        while IFS= read -r -d '' f; do
            if head -c4 "$f" 2>/dev/null | grep -q $'\x7fELF'; then printf '%s\n' "$f"; fi
        done
}
# Copied libraries go next to the Qt libraries: Qt and its plugins find them
# through their own RUNPATH, and the copies get RUNPATH=$ORIGIN for theirs.
for _ in 1 2 3 4 5; do
    added=0
    while IFS= read -r elf; do
        while read -r name _arrow path _rest; do
            case "$path" in /*) ;; *) continue ;; esac
            case "$path" in "$APPDIR"/*) continue ;; esac
            is_excluded "$name" && continue
            [ -e "$QT/lib/$name" ] && continue
            echo "  $name (for ${elf#"$APPDIR"/})"
            cp -L "$path" "$QT/lib/$name"
            chmod 644 "$QT/lib/$name"
            patchelf --set-rpath '$ORIGIN' "$QT/lib/$name"
            added=1
        done < <({ env -u LD_LIBRARY_PATH ldd "$elf" 2>/dev/null || true; } | grep '=>' || true)
    done < <(elfs)
    [ "$added" = 0 ] && break
done
missing="$(elfs | while IFS= read -r elf; do
    { env -u LD_LIBRARY_PATH ldd "$elf" 2>/dev/null || true; } |
        sed -n "s|^\s*\(\S*\) => not found|\1 (${elf#"$APPDIR"/})|p"
done)"
if [ -n "$missing" ]; then
    echo "Unresolved libraries (install them on the build host):" >&2
    echo "$missing" >&2
    exit 1
fi
for p in platforms/libqxcb.so platforms/libqwayland.so; do
    [ -e "$QT/plugins/$p" ] || { echo "Missing Qt platform plugin $p" >&2; exit 1; }
done

# --- launcher and desktop integration -----------------------------------------
log "AppDir layout"
install -Dm755 "$HERE/AppRun" "$APPDIR/AppRun"
install -Dm644 /dev/stdin "$APPDIR/usr/bin/$APP_ID" <<'EOF'
# Repokase entry point; AppRun starts it with the bundled Python (python -I).
import sys

from repokase.__main__ import main

sys.exit(main())
EOF
install -d "$APPDIR/usr/share/applications"
{ cat "$HERE/../$APP_ID.desktop"; echo "X-AppImage-Version=$version"; } \
    > "$APPDIR/usr/share/applications/$APP_ID.desktop"
cp "$APPDIR/usr/share/applications/$APP_ID.desktop" "$APPDIR/$APP_ID.desktop"
for size in 16 24 32 48 64 128 256 512; do
    icon="$HERE/../icons/hicolor/${size}x${size}/apps/$APP_ID.png"
    install -Dm644 "$icon" "$APPDIR/usr/share/icons/hicolor/${size}x${size}/apps/$APP_ID.png"
done
install -Dm644 "$HERE/../icons/hicolor/scalable/apps/$APP_ID.svg" \
    "$APPDIR/usr/share/icons/hicolor/scalable/apps/$APP_ID.svg"
# Root icon as PNG: integrators and appimagelint read its size.
cp "$APPDIR/usr/share/icons/hicolor/256x256/apps/$APP_ID.png" "$APPDIR/$APP_ID.png"
ln -s "usr/share/icons/hicolor/256x256/apps/$APP_ID.png" "$APPDIR/.DirIcon"
install -Dm644 "$HERE/../com.ninepointlabs.repokase.metainfo.xml" \
    "$APPDIR/usr/share/metainfo/com.ninepointlabs.repokase.metainfo.xml"
install -Dm644 "$APP_SRC/LICENSE" "$APPDIR/usr/share/licenses/$APP_ID/LICENSE"

# --- AppImage -----------------------------------------------------------------
# appimagetool only looks for <desktop id>.appdata.xml, while AppStream wants
# the file named after the component id (com.ninepointlabs.repokase), so it
# would only warn that metadata is missing. smoke-test.sh validates it instead.
log "appimagetool"
target="$OUT/$APP_ID-$version-x86_64.AppImage"
rm -f "$target" "$target.zsync" "$target.sha256"
(cd "$OUT" && ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$TOOLS/appimagetool.AppImage" \
    --runtime-file "$TOOLS/runtime-x86_64" --no-appstream -u "$UPDATE_INFO" "$APPDIR" "$target")
[ -f "$target.zsync" ] || { echo "appimagetool wrote no .zsync (is zsyncmake installed?)" >&2; exit 1; }
(cd "$OUT" && sha256sum "$(basename "$target")" > "$(basename "$target").sha256")

log "Done"
ls -l "$OUT"
du -sh "$APPDIR"
