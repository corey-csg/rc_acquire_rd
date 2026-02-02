from __future__ import annotations

from acquire.pipeline.filter import should_enrich, should_notify, is_diff_too_small


def test_should_enrich_actionable():
    assert should_enrich("RFI") is True
    assert should_enrich("RFP") is True
    assert should_enrich("ACTIONABLE") is True


def test_should_not_enrich_informational():
    assert should_enrich("INFORMATIONAL") is False
    assert should_enrich("IRRELEVANT") is False


def test_should_notify_actionable():
    assert should_notify("RFI") is True
    assert should_notify("RFP") is True


def test_diff_too_small():
    assert is_diff_too_small(None) is True
    assert is_diff_too_small("") is True
    assert is_diff_too_small("short") is True
    assert is_diff_too_small("x" * 100) is False
