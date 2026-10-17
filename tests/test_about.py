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
