"""The About dialog's facts (no Qt)."""

from pathlib import Path

import repokase

ROOT = Path(__file__).resolve().parents[1]


def test_bundled_license_is_the_license():
    # The app ships its own copy for the About dialog; it must not drift.
    bundled = ROOT / "src" / "repokase" / "assets" / "LICENSE.txt"
    assert bundled.read_text() == (ROOT / "LICENSE").read_text()


def test_facts_agree_with_the_license():
    license_text = (ROOT / "LICENSE").read_text()
    assert license_text.startswith("MIT License")
    assert repokase.LICENSE_NAME == "MIT License"
    assert repokase.COPYRIGHT.replace("©", "Copyright (c)") in license_text
    assert repokase.SUPPORT_EMAIL == "help@ninepointlabs.com"
    assert repokase.ORGANIZATION == "Nine Point Labs"


def test_readme_lists_every_shortcut_in_the_about_dialog():
    import re

    qml = (ROOT / "src" / "repokase" / "qml" / "views" / "AboutDialog.qml").read_text()
    rows = re.findall(r'\["([^"]*)", "([^"]*)"\]', qml[qml.index("shortcuts:"):])
    readme = (ROOT / "README.md").read_text()
    table = readme[readme.index("| Keys | Action |"):]
    table = table[:table.index("\n\n")]
    spans = re.findall(r"`([^`]+)`", table)
    missing = []
    for keys, action in rows:
        if not action:  # section header
            continue
        for token in re.split(r"[\s/]+", keys):
            if token in ("", "…"):
                continue
            # One-character keys must be their own `span`; longer ones may be
            # part of a combined one (`Shift+↓↑` covers Shift+↓ and ↑).
            if not any(span == token or (len(token) > 1 and token in span) for span in spans) and not (
                len(token) == 1 and any(token in span and "+" in span for span in spans)
            ):
                missing.append(f"{token} ({action})")
    assert not missing, missing
