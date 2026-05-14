from __future__ import annotations

import pytest

from timer_entry.calendar import is_trading_day_excluded, is_us_uk_dst_mismatch_day


def test_us_uk_dst_mismatch_day_matches_spring_gap() -> None:
    assert is_us_uk_dst_mismatch_day("2024-03-09", "Europe/London") is False
    assert is_us_uk_dst_mismatch_day("2024-03-10", "Europe/London") is True
    assert is_us_uk_dst_mismatch_day("2024-03-30", "Europe/London") is True
    assert is_us_uk_dst_mismatch_day("2024-03-31", "Europe/London") is False


def test_us_uk_dst_mismatch_day_matches_autumn_gap() -> None:
    assert is_us_uk_dst_mismatch_day("2024-10-26", "Europe/London") is False
    assert is_us_uk_dst_mismatch_day("2024-10-27", "Europe/London") is True
    assert is_us_uk_dst_mismatch_day("2024-11-02", "Europe/London") is True
    assert is_us_uk_dst_mismatch_day("2024-11-03", "Europe/London") is False


def test_us_uk_dst_mismatch_day_matches_2025_gaps() -> None:
    assert is_us_uk_dst_mismatch_day("2025-03-08", "Europe/London") is False
    assert is_us_uk_dst_mismatch_day("2025-03-09", "Europe/London") is True
    assert is_us_uk_dst_mismatch_day("2025-03-29", "Europe/London") is True
    assert is_us_uk_dst_mismatch_day("2025-03-30", "Europe/London") is False
    assert is_us_uk_dst_mismatch_day("2025-03-31", "Europe/London") is False
    assert is_us_uk_dst_mismatch_day("2025-10-25", "Europe/London") is False
    assert is_us_uk_dst_mismatch_day("2025-10-26", "Europe/London") is True
    assert is_us_uk_dst_mismatch_day("2025-11-01", "Europe/London") is True
    assert is_us_uk_dst_mismatch_day("2025-11-02", "Europe/London") is False


def test_us_uk_dst_mismatch_does_not_exclude_tokyo_session() -> None:
    assert is_trading_day_excluded("2024-03-15", "Asia/Tokyo", ["us_uk_dst_mismatch"]) is False


def test_unknown_exclude_window_fails_closed() -> None:
    with pytest.raises(ValueError):
        is_trading_day_excluded("2024-03-15", "Europe/London", ["unknown"])
