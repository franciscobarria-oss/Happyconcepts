"""Kitchen Checks: when a checklist is due. Pure Python (tests/test_compliance_schedule.py).

A Checklist Schedule is a plain dict here:
	frequency: "Daily" | "Selected weekdays" | "Monthly" | "Every N hours"
	weekdays: set of "Mon".."Sun" (Selected weekdays)
	day_of_month: 1-31 (Monthly; a short month uses its last day)
	start_time, due_time: "HH:MM" or "HH:MM:SS"; a due time at or before the start time ends the next day
	every_hours: N (Every N hours: windows of N hours from start_time until due_time)
	grace_minutes: minutes after the due time before a run counts as Overdue
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, time, timedelta

FREQUENCIES = ("Daily", "Selected weekdays", "Monthly", "Every N hours")
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

# run statuses
PENDING, IN_PROGRESS, OVERDUE, MISSED = "Pending", "In progress", "Overdue", "Missed"
COMPLETED, WITH_ISSUES, REVIEWED = "Completed", "Completed with issues", "Reviewed"
OPEN_STATUSES = (PENDING, IN_PROGRESS, OVERDUE, MISSED)
DONE_STATUSES = (COMPLETED, WITH_ISSUES, REVIEWED)


def parse_time(value) -> time:
	"""'07:30', '07:30:00', a time or a timedelta (how MariaDB returns Time fields)."""
	if isinstance(value, time):
		return value
	if isinstance(value, timedelta):
		secs = int(value.total_seconds()) % 86400
		return time(secs // 3600, secs % 3600 // 60, secs % 60)
	parts = [int(p) for p in str(value).strip().split(".")[0].split(":")]
	while len(parts) < 3:
		parts.append(0)
	return time(*parts[:3])


def runs_on(schedule: dict, day: date) -> bool:
	freq = schedule.get("frequency") or "Daily"
	if freq in ("Daily", "Every N hours"):
		return True
	if freq == "Selected weekdays":
		return WEEKDAYS[day.weekday()] in set(schedule.get("weekdays") or ())
	if freq == "Monthly":
		want = int(schedule.get("day_of_month") or 1)
		last = calendar.monthrange(day.year, day.month)[1]
		return day.day == min(max(want, 1), last)
	raise ValueError(f"unknown frequency {freq!r}")


def windows(schedule: dict, day: date) -> list[tuple[datetime, datetime]]:
	"""The due windows (start, due) that start on this day."""
	if not runs_on(schedule, day):
		return []
	start = datetime.combine(day, parse_time(schedule.get("start_time") or "00:00"))
	due = datetime.combine(day, parse_time(schedule.get("due_time") or "23:59"))
	if due <= start:
		due += timedelta(days=1)
	if (schedule.get("frequency") or "Daily") != "Every N hours":
		return [(start, due)]
	step = timedelta(hours=int(schedule.get("every_hours") or 0))
	if step <= timedelta(0):
		raise ValueError("every_hours must be at least 1")
	out, s = [], start
	while s < due:
		out.append((s, min(s + step, due)))
		s += step
	return out


def windows_started(schedule: dict, now: datetime, look_back_days: int = 1) -> list[tuple[datetime, datetime]]:
	"""Windows that have started by `now`, from yesterday on (a window can cross midnight)."""
	out = []
	for back in range(look_back_days, -1, -1):
		day = now.date() - timedelta(days=back)
		out += [w for w in windows(schedule, day) if w[0] <= now]
	return out


def run_key(schedule_name: str, window_start: datetime) -> str:
	return f"{schedule_name}|{window_start:%Y-%m-%d %H:%M}"


def runs_to_create(schedules: dict[str, dict], existing: set[str], now: datetime) -> list[dict]:
	"""New runs for windows that have started and have no run yet.
	schedules: {schedule name: schedule dict}; existing: run_key()s already on the site."""
	out = []
	for name, sch in schedules.items():
		for start, due in windows_started(sch, now):
			key = run_key(name, start)
			if key not in existing:
				out.append({"schedule": name, "window_start": start, "window_end": due, "key": key})
	return out


def open_status(now: datetime, window_end: datetime, grace_minutes: int, missed_after_hours: float,
                started: bool = False) -> str:
	"""Status of a run nobody has signed yet."""
	late_from = window_end + timedelta(minutes=int(grace_minutes or 0))
	if now >= late_from + timedelta(hours=float(missed_after_hours or 0)):
		return MISSED
	if now >= late_from:
		return OVERDUE
	return IN_PROGRESS if started else PENDING


def is_late(signed_at: datetime, window_end: datetime, grace_minutes: int) -> bool:
	return signed_at > window_end + timedelta(minutes=int(grace_minutes or 0))


def band(status: str) -> str:
	"""Kiosk band for a run: overdue / due / done."""
	if status in (OVERDUE, MISSED):
		return "overdue"
	if status in DONE_STATUSES:
		return "done"
	return "due"


def summary(statuses: list[str]) -> dict:
	"""Counts for the manager card: total, done, issues, overdue (missed included), open, done_pct."""
	total = len(statuses)
	done = sum(1 for s in statuses if s in DONE_STATUSES)
	return {
		"total": total,
		"done": done,
		"issues": sum(1 for s in statuses if s == WITH_ISSUES),
		"overdue": sum(1 for s in statuses if s in (OVERDUE, MISSED)),
		"open": sum(1 for s in statuses if s in (PENDING, IN_PROGRESS)),
		"done_pct": round(100 * done / total) if total else None,
	}
