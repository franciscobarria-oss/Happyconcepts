from datetime import date, datetime
import hashlib

import pytest

from happy_kitchen.hk_operations import team as t


def test_hourly_cost_monthly_with_mpf():
	# 20,000 + 1,000 MPF over 24 x 9
	assert t.hourly_cost(20000, 24, 9) == round(21000 / 216, 2)


def test_hourly_cost_mpf_capped():
	# MPF on 40,000 would be 2,000; capped at 1,500
	assert t.hourly_cost(40000, 24, 9) == round(41500 / 216, 2)


def test_hourly_cost_hourly_staff():
	assert t.hourly_cost(hourly_rate=60) == 63.0
	assert t.hourly_cost(20000, 24, 9, hourly_rate=60) == 63.0  # hourly wins


def test_hourly_cost_incomplete():
	assert t.hourly_cost(20000, 0, 9) == 0
	assert t.hourly_cost() == 0


def test_pin():
	assert t.pin_hash("HR-EMP-00001", "1234") == hashlib.sha256(b"HR-EMP-00001:1234").hexdigest()
	assert t.valid_pin("0042")
	for bad in ("123", "12345", "12a4", None, 1234):
		assert not t.valid_pin(bad)


def test_roster_cycle():
	assert t.next_shift(None) == "Early"
	assert t.next_shift("Early") == "Late"
	assert t.next_shift("Late") is None
	assert t.next_shift("Night") is None


def test_next_log_type():
	assert t.next_log_type(None) == "IN"
	assert t.next_log_type("OUT") == "IN"
	assert t.next_log_type("IN") == "OUT"


@pytest.mark.parametrize("joined,on,days", [
	(date(2026, 3, 1), date(2026, 12, 31), 0),
	(date(2025, 3, 1), date(2026, 3, 1), 7),
	(date(2024, 3, 1), date(2026, 3, 1), 7),
	(date(2023, 3, 1), date(2026, 3, 1), 8),
	(date(2010, 1, 1), date(2026, 6, 1), 14),
	(date(2025, 3, 2), date(2026, 3, 1), 0),  # one day short of a year
])
def test_annual_leave(joined, on, days):
	assert t.annual_leave_days(joined, on) == days


def test_holidays_inside_list_range_and_valid():
	start, end = t.HOLIDAY_LIST_RANGE
	for d in t.HOLIDAYS:
		datetime.strptime(d, "%Y-%m-%d")
		assert start <= d <= end
	assert len(t.HOLIDAYS) == 30


def test_overtime_activity_rate_is_80_plus_mpf():
	assert t.OVERTIME_ACTIVITY_RATE == 80 * (1 + t.MPF_RATE)


def test_shift_types_match_roster():
	assert set(t.SHIFT_TYPES) == set(t.SHIFTS)


def test_shift_hours():
	assert t.shift_hours(*t.SHIFT_TYPES["Early"][:2]) == 9
	assert t.shift_hours("11:00", "20:30") == 9.5
