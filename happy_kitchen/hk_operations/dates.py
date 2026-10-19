"""Kitchen date maths (P15b), plain Python so it can be unit-tested.

- Opened products: "use within N hours" counts from the minute the pack is
  opened; "use within N days" counts the opening day as day 1 and ends at
  23:59 of the last day (opened Mon 14:00, 3 days -> use by Wed 23:59).
- Batches: use by = made on + the item's shelf life in days (the same rule as
  the best-before date on product labels).
- Lot numbers: L + yymmdd of the day made, -2, -3 ... for later runs that day.
"""

from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta

HOURS, DAYS = "Hours", "Days"
UNITS = (HOURS, DAYS)
STORAGE = ("Ambient", "Chilled", "Frozen")
STORAGE_ZH = {"Ambient": "常溫", "Chilled": "冷藏", "Frozen": "冷凍"}
END_OF_DAY = time(23, 59)


def opened_use_by(opened_at: datetime, value, unit: str | None) -> datetime | None:
	"""When an opened product must be used by; None when the item has no open life."""
	try:
		value = float(value or 0)
	except (TypeError, ValueError):
		value = 0.0
	if value <= 0:
		return None
	start = opened_at.replace(second=0, microsecond=0)
	if (unit or DAYS) == HOURS:
		return start + timedelta(minutes=math.floor(value * 60))
	days = max(1, int(value))  # whole days; 1 = the day it was opened
	return datetime.combine(start.date() + timedelta(days=days - 1), END_OF_DAY)


def batch_use_by(made_on: date, shelf_life_days) -> date | None:
	days = int(shelf_life_days or 0)
	return made_on + timedelta(days=days) if days > 0 else None


def lot_code(made_on: date, run: int = 1) -> str:
	"""L261019 for the first run of the day, L261019-2 for the second..."""
	base = "L" + made_on.strftime("%y%m%d")
	return base if run <= 1 else f"{base}-{run}"


def next_lot(made_on: date, taken) -> str:
	"""The first lot code for that day not in `taken`."""
	taken = set(taken or ())
	run = 1
	while lot_code(made_on, run) in taken:
		run += 1
	return lot_code(made_on, run)


def date_state(use_by, now: datetime) -> str:
	"""past (use-by has passed), today (ends today), soon (tomorrow) or ok.
	A date-only use-by (batches) lasts until the end of that day."""
	if not use_by:
		return "ok"
	if isinstance(use_by, datetime):
		end = use_by
	else:
		end = datetime.combine(use_by, END_OF_DAY)
	if end < now:
		return "past"
	if end.date() == now.date():
		return "today"
	if end.date() == now.date() + timedelta(days=1):
		return "soon"
	return "ok"


def fmt_when(value) -> str:
	"""19/10 14:30 for a time, 19/10/26 for a date (small labels have little room)."""
	if not value:
		return ""
	if isinstance(value, datetime):
		return value.strftime("%d/%m %H:%M")
	return value.strftime("%d/%m/%y")
