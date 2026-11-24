#!/usr/bin/env bash
# Build repokase_<version>_amd64.deb and repokase-<version>-1.x86_64.rpm (each
# with a .sha256) from the AppDir that packaging/appimage/build.sh leaves in
# build/appimage/AppDir.
#
#   build-packages.sh [--appdir DIR] [--out DIR]
#
# Both packages carry the same self-contained tree as the AppImage (its own
# Python 3.12 and Qt, tested by smoke-test.sh) under /opt/repokase, with
# /usr/bin/repokase, the desktop entry, icons, AppStream metadata and the
# traffic timer in the usual places. They depend only on the host libraries
# the AppImage also takes from the system (the AppImage excludelist: glibc,
# libstdc++, GL/EGL, fontconfig, freetype, X11/xcb, wayland-client, ...), so
# the same glibc 2.35 floor applies: Ubuntu 22.04+, Debian 12+, Fedora,
# openSUSE.
#
# nfpm is downloaded once and pinned by SHA-256.
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
WORK="${WORK:-$REPO/build/linux}"
APP_ID=repokase

NFPM_VERSION=2.48.0
NFPM_URL="https://github.com/goreleaser/nfpm/releases/download/v$NFPM_VERSION/nfpm_${NFPM_VERSION}_Linux_x86_64.tar.gz"
NFPM_SHA=6d7f9a28b2f397934403950fcbba83f598b08d02edbe79a0815b3b4897341750

log() { printf '\n==> %s\n' "$*"; }

[ -x "$APPDIR/opt/python3.12/bin/python3.12" ] || { echo "No AppDir at $APPDIR (run packaging/appimage/build.sh first)" >&2; exit 1; }
version="$(sed -n 's/^X-AppImage-Version=//p' "$APPDIR/$APP_ID.desktop")"
[ -n "$version" ] || { echo "No X-AppImage-Version in $APPDIR/$APP_ID.desktop" >&2; exit 1; }
log "Repokase $version from $APPDIR"

mkdir -p "$WORK"
nfpm_tgz="$WORK/nfpm.tar.gz"
if ! { [ -f "$nfpm_tgz" ] && echo "$NFPM_SHA  $nfpm_tgz" | sha256sum -c --quiet - 2>/dev/null; }; then
    curl -fsSL --retry 3 -o "$nfpm_tgz.part" "$NFPM_URL"
    echo "$NFPM_SHA  $nfpm_tgz.part" | sha256sum -c --quiet - || { echo "Checksum mismatch for $NFPM_URL" >&2; exit 1; }
    mv "$nfpm_tgz.part" "$nfpm_tgz"
fi
tar -xzf "$nfpm_tgz" -C "$WORK" nfpm
NFPM="$WORK/nfpm"

# --- staging tree ---------------------------------------------------------------
log "Staging"
STAGE="$WORK/stage"
rm -rf "$STAGE"
mkdir -p "$STAGE/opt/$APP_ID"
# The AppDir's own layout (opt/python3.12, usr/lib, usr/bin/repokase) is kept,
# since Python, Qt and the copied libraries find each other through relative
# RUNPATHs. AppRun and the AppImage-only root files are left out.
cp -a "$APPDIR/opt" "$STAGE/opt/$APP_ID/opt"
mkdir -p "$STAGE/opt/$APP_ID/usr"
cp -a "$APPDIR/usr/lib" "$APPDIR/usr/bin" "$STAGE/opt/$APP_ID/usr/"

install -Dm755 /dev/stdin "$STAGE/usr/bin/$APP_ID" <<EOF
#!/bin/sh
# Repokase, with its bundled Python and Qt in /opt/$APP_ID.
exec /opt/$APP_ID/opt/python3.12/bin/python3.12 -I /opt/$APP_ID/usr/bin/$APP_ID "\$@"
EOF
install -Dm644 "$REPO/packaging/$APP_ID.desktop" "$STAGE/usr/share/applications/$APP_ID.desktop"
cp -a "$APPDIR/usr/share/icons" "$STAGE/usr/share/icons"
install -Dm644 "$APPDIR/usr/share/metainfo/com.ninepointlabs.repokase.metainfo.xml" \
    "$STAGE/usr/share/metainfo/com.ninepointlabs.repokase.metainfo.xml"
install -Dm644 "$REPO/packaging/systemd/repokase-traffic.service" "$STAGE/usr/lib/systemd/user/repokase-traffic.service"
install -Dm644 "$REPO/packaging/systemd/repokase-traffic.timer" "$STAGE/usr/lib/systemd/user/repokase-traffic.timer"
install -Dm644 "$APPDIR/usr/share/licenses/$APP_ID/LICENSE" "$STAGE/usr/share/licenses/$APP_ID/LICENSE"
install -Dm644 "$APPDIR/usr/share/licenses/$APP_ID/LICENSE" "$STAGE/usr/share/doc/$APP_ID/copyright"
find "$STAGE" -name __pycache__ -type d -prune -exec rm -rf {} +

# --- nfpm -----------------------------------------------------------------------
# Debian has no soname dependencies, so the .deb names packages (present under
# these names from Ubuntu 22.04 / Debian 12 on). RPM resolves sonames, which
# works the same on Fedora and openSUSE.
cat > "$WORK/nfpm.yaml" <<EOF
name: $APP_ID
arch: amd64
platform: linux
version: $version
release: 1
section: devel
priority: optional
maintainer: Nine Point Labs <179739321+ninepointlabs@users.noreply.github.com>
vendor: Nine Point Labs
homepage: https://github.com/ninepointlabs/repokase
license: MIT
description: |-
  Your repos, chef's choice. A desktop app for managing GitHub repositories.
  Every repository you own or collaborate on, with stats, CI status, traffic
  history and GitHub Actions, in one keyboard-driven window. Bundles its own
  Python and Qt.
contents:
  - src: $STAGE/opt/$APP_ID
    dst: /opt/$APP_ID
    type: tree
  - src: $STAGE/usr
    dst: /usr
    type: tree
overrides:
  deb:
    depends:
      - libc6 (>= 2.35)
      - libstdc++6
      - libgcc-s1
      - libegl1
      - libgl1
      - libfontconfig1
      - libfreetype6
      - libgpg-error0
      - libcom-err2
      - libuuid1
      - libwayland-client0
      - libx11-6
      - libx11-xcb1
      - libxcb1
      - zlib1g
    recommends:
      - xdg-utils
    suggests:
      - gnome-keyring
  rpm:
    depends:
      - libc.so.6(GLIBC_2.35)(64bit)
      - libstdc++.so.6()(64bit)
      - libgcc_s.so.1()(64bit)
      - libEGL.so.1()(64bit)
      - libGL.so.1()(64bit)
      - libfontconfig.so.1()(64bit)
      - libfreetype.so.6()(64bit)
      - libgpg-error.so.0()(64bit)
      - libcom_err.so.2()(64bit)
      - libuuid.so.1()(64bit)
      - libwayland-client.so.0()(64bit)
      - libX11.so.6()(64bit)
      - libX11-xcb.so.1()(64bit)
      - libxcb.so.1()(64bit)
      - libz.so.1()(64bit)
    recommends:
      - xdg-utils
rpm:
  group: Development/Tools
  summary: Your repos, chef's choice. A desktop app for managing GitHub repositories
  compression: zstd
deb:
  compression: xz
EOF

for packager in deb rpm; do
    log "$packager"
    "$NFPM" package --config "$WORK/nfpm.yaml" --packager "$packager" --target "$OUT/"
done
deb="$OUT/${APP_ID}_${version}-1_amd64.deb"
rpm="$OUT/$APP_ID-$version-1.x86_64.rpm"
for f in "$deb" "$rpm"; do
    [ -f "$f" ] || { echo "Expected $f; got:" >&2; ls -l "$OUT" >&2; exit 1; }
    (cd "$OUT" && sha256sum "$(basename "$f")" > "$(basename "$f").sha256")
done

log "Done"
ls -l "$OUT"
