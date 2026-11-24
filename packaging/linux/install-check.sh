#!/usr/bin/env bash
# After installing the .deb, .rpm or Flatpak: check that Repokase is in place
# and starts. Runs headless (Qt offscreen platform), as root in a container or
# as a user on a CI runner.
#
#   install-check.sh <version> <command...>
#   e.g. install-check.sh 0.2.6 repokase
#        install-check.sh 0.2.6 flatpak run com.ninepointlabs.repokase
set -uo pipefail

version="${1:?usage: $0 <version> <command...>}"
shift
[ $# -gt 0 ] || { echo "usage: $0 <version> <command...>" >&2; exit 2; }
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
failures=0
pass() { printf 'PASS  %s\n' "$*"; }
fail() { printf 'FAIL  %s\n' "$*"; failures=$((failures + 1)); }

out="$("$@" --version 2>&1)"
if [ "$out" = "Repokase $version" ]; then
    pass "--version: $out"
else
    fail "--version printed: $out"
fi

# A fresh, empty HOME, except under flatpak, which finds its --user
# installation in HOME and already gives the app its own data directories.
if [ "$1" = flatpak ]; then
    QT_QPA_PLATFORM=offscreen timeout 90 "$@" --self-test >"$T/self-test.log" 2>&1
else
    mkdir -p "$T/home" "$T/run" && chmod 700 "$T/run"
    HOME="$T/home" XDG_RUNTIME_DIR="$T/run" QT_QPA_PLATFORM=offscreen \
        timeout 90 "$@" --self-test >"$T/self-test.log" 2>&1
fi
rc=$?
bad="$(grep -E 'Traceback|QML warning|cannot open shared|undefined symbol|qt\.qpa\.plugin|Could not (load|find)' "$T/self-test.log")"
if [ "$rc" = 0 ] && [ -z "$bad" ] && grep -q '^self-test: .*visible=True' "$T/self-test.log"; then
    pass "headless start: $(grep '^self-test:' "$T/self-test.log")"
else
    fail "headless start (exit $rc)"
    sed 's/^/      /' "$T/self-test.log"
fi

if [ "$failures" -eq 0 ]; then
    echo "All checks passed."
else
    echo "$failures check(s) failed."
    exit 1
fi
