from datetime import date, datetime, time, timedelta

import pytest

from happy_kitchen.hk_compliance import schedule as s

MON = date(2026, 11, 2)  # a Monday


def test_parse_time_accepts_strings_and_timedelta():
	assert s.parse_time("7:30") == time(7, 30)
	assert s.parse_time("07:30:15.000") == time(7, 30, 15)
	assert s.parse_time(timedelta(hours=22, minutes=5)) == time(22, 5)


def test_daily_window():
	sch = {"frequency": "Daily", "start_time": "06:30", "due_time": "07:30"}
	assert s.windows(sch, MON) == [(datetime(2026, 11, 2, 6, 30), datetime(2026, 11, 2, 7, 30))]


def test_window_crossing_midnight():
	sch = {"frequency": "Daily", "start_time": "22:00", "due_time": "01:00"}
	assert s.windows(sch, MON) == [(datetime(2026, 11, 2, 22), datetime(2026, 11, 3, 1))]


def test_selected_weekdays():
	sch = {"frequency": "Selected weekdays", "weekdays": {"Mon", "Thu"}, "start_time": "14:00", "due_time": "16:00"}
	assert s.runs_on(sch, MON) and not s.runs_on(sch, MON + timedelta(days=1))
	assert s.runs_on(sch, MON + timedelta(days=3))


def test_monthly_uses_last_day_of_short_month():
	sch = {"frequency": "Monthly", "day_of_month": 31, "start_time": "09:00", "due_time": "17:00"}
	assert s.runs_on(sch, date(2026, 11, 30)) and not s.runs_on(sch, date(2026, 11, 29))
	assert s.runs_on(sch, date(2026, 12, 31)) and not s.runs_on(sch, date(2026, 12, 30))


def test_every_n_hours():
	sch = {"frequency": "Every N hours", "every_hours": 4, "start_time": "08:00", "due_time": "18:00"}
	w = s.windows(sch, MON)
	assert [(a.hour, b.hour) for a, b in w] == [(8, 12), (12, 16), (16, 18)]
	with pytest.raises(ValueError):
		s.windows({**sch, "every_hours": 0}, MON)


def test_runs_to_create_only_started_and_new():
	schedules = {
		"open": {"frequency": "Daily", "start_time": "06:30", "due_time": "07:30"},
		"close": {"frequency": "Daily", "start_time": "22:00", "due_time": "01:00"},
	}
	now = datetime(2026, 11, 2, 7, 0)
	new = s.runs_to_create(schedules, set(), now)
	keys = {r["key"] for r in new}
	# yesterday's and today's opening, yesterday's closing; today's closing has not started
	assert keys == {"open|2026-11-01 06:30", "open|2026-11-02 06:30", "close|2026-11-01 22:00"}
	assert s.runs_to_create(schedules, keys, now) == []


def test_open_status():
	end = datetime(2026, 11, 2, 7, 30)
	assert s.open_status(datetime(2026, 11, 2, 7, 0), end, 15, 4) == s.PENDING
	assert s.open_status(datetime(2026, 11, 2, 7, 0), end, 15, 4, started=True) == s.IN_PROGRESS
	assert s.open_status(datetime(2026, 11, 2, 7, 44), end, 15, 4) == s.PENDING
	assert s.open_status(datetime(2026, 11, 2, 7, 45), end, 15, 4) == s.OVERDUE
	assert s.open_status(datetime(2026, 11, 2, 11, 45), end, 15, 4) == s.MISSED


def test_is_late_and_band():
	end = datetime(2026, 11, 2, 7, 30)
	assert not s.is_late(datetime(2026, 11, 2, 7, 45), end, 15)
	assert s.is_late(datetime(2026, 11, 2, 7, 46), end, 15)
	assert s.band(s.MISSED) == "overdue" and s.band(s.REVIEWED) == "done" and s.band(s.PENDING) == "due"


def test_summary():
	r = s.summary([s.COMPLETED, s.WITH_ISSUES, s.OVERDUE, s.MISSED, s.PENDING])
	assert r == {"total": 5, "done": 2, "issues": 1, "overdue": 2, "open": 1, "done_pct": 40}
	assert s.summary([])["done_pct"] is None
