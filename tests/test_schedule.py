from datetime import time

from schedule import is_within_quiet_hours, parse_hhmm


def test_parse_hhmm_valid():
    assert parse_hhmm("23:15") == time(23, 15)


def test_parse_hhmm_none_for_empty_string():
    assert parse_hhmm("") is None


def test_parse_hhmm_none_for_none():
    assert parse_hhmm(None) is None


def test_quiet_hours_disabled_when_either_bound_missing():
    assert is_within_quiet_hours(time(2, 0), None, time(6, 0)) is False
    assert is_within_quiet_hours(time(2, 0), time(23, 0), None) is False


def test_quiet_hours_disabled_when_start_equals_end():
    assert is_within_quiet_hours(time(12, 0), time(23, 0), time(23, 0)) is False


def test_quiet_hours_same_day_window():
    start, end = time(1, 0), time(5, 0)
    assert is_within_quiet_hours(time(3, 0), start, end) is True
    assert is_within_quiet_hours(time(0, 30), start, end) is False
    assert is_within_quiet_hours(time(6, 0), start, end) is False


def test_quiet_hours_overnight_window_late_and_early():
    start, end = time(23, 0), time(6, 0)
    assert is_within_quiet_hours(time(23, 30), start, end) is True
    assert is_within_quiet_hours(time(3, 0), start, end) is True
    assert is_within_quiet_hours(time(12, 0), start, end) is False


def test_quiet_hours_boundary_start_inclusive_end_exclusive():
    start, end = time(23, 0), time(6, 0)
    assert is_within_quiet_hours(time(23, 0), start, end) is True
    assert is_within_quiet_hours(time(6, 0), start, end) is False
