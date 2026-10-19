#!/usr/bin/env bash
# Build (and smoke-test) the AppImage locally in an ubuntu:22.04 container,
# the same base CI uses. Output lands in dist-appimage/.
#
#   packaging/appimage/docker-build.sh [build.sh args]
set -euo pipefail
REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
docker run --rm -v "$REPO:/repo" -w /repo -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" \
    ubuntu:22.04 bash -euo pipefail -c '
        export DEBIAN_FRONTEND=noninteractive
        apt-get update -qq
        grep -v "^#" packaging/appimage/build-deps.txt | xargs apt-get install -y -qq --no-install-recommends >/dev/null
        groupadd -g "$HOST_GID" builder 2>/dev/null || true
        useradd -m -u "$HOST_UID" -g "$HOST_GID" builder
        su builder -c "packaging/appimage/build.sh $* && packaging/appimage/smoke-test.sh dist-appimage/repokase-*-x86_64.AppImage"
    ' _ "$@"
