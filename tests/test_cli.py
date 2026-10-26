"""Command-line parsing (no Qt)."""

import pytest

from repokase.__main__ import _parse_args


def test_if_due_needs_snapshot_traffic(capsys):
    with pytest.raises(SystemExit) as exit_:
        _parse_args(["--if-due"])
    assert exit_.value.code == 2
    assert "--if-due only works with --snapshot-traffic" in capsys.readouterr().err


def test_if_due_with_snapshot_traffic():
    args = _parse_args(["--snapshot-traffic", "--if-due"])
    assert args.snapshot_traffic and args.if_due
