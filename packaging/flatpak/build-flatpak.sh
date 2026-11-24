#!/usr/bin/env bash
# Build repokase-<version>-x86_64.flatpak (+ .sha256), a self-hosted Flatpak
# bundle, from the AppDir that packaging/appimage/build.sh leaves in
# build/appimage/AppDir. Needs flatpak, flatpak-builder and the
# org.freedesktop.Platform/Sdk 25.08 from Flathub (CI installs them).
#
#   build-flatpak.sh [--appdir DIR] [--out DIR]
set -euo pipefail

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd -- "$HERE/../.." && pwd)"
APPDIR="$REPO/build/appimage/AppDir"
OUT="$REPO/dist-packages"
while [ $# -gt 0 ]; do
    case "$1" in
        --appdir) APPDIR="$(cd -- "$2" && pwd)"; shift 2 ;;
        --out) OUT="$2"; shift 2 ;;
        *) echo "usage: $0 [--appdir DIR] [--out DIR]" >&2; exit 2 ;;
    esac
done
mkdir -p "$OUT" && OUT="$(cd -- "$OUT" && pwd)"
WORK="${WORK:-$REPO/build/flatpak}"
APP_FQID=com.ninepointlabs.repokase

version="$(sed -n 's/^X-AppImage-Version=//p' "$APPDIR/repokase.desktop")"
[ -n "$version" ] || { echo "No X-AppImage-Version in $APPDIR/repokase.desktop" >&2; exit 1; }
echo "==> Repokase $version from $APPDIR"

rm -rf "$WORK"
mkdir -p "$WORK/src"
cp "$HERE/$APP_FQID.yml" "$WORK/src/"
cp -a "$APPDIR" "$WORK/src/appdir"

flatpak-builder --user --force-clean --disable-rofiles-fuse \
    --state-dir="$WORK/state" --repo="$WORK/repo" \
    --default-branch=stable --subject="Repokase $version" \
    "$WORK/build" "$WORK/src/$APP_FQID.yml"

bundle="$OUT/repokase-$version-x86_64.flatpak"
flatpak build-bundle --runtime-repo=https://dl.flathub.org/repo/flathub.flatpakrepo \
    "$WORK/repo" "$bundle" "$APP_FQID" stable
(cd "$OUT" && sha256sum "$(basename "$bundle")" > "$(basename "$bundle").sha256")
ls -l "$OUT"
