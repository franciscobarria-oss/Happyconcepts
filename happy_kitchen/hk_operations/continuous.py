"""Plain-Python rules for the Hong Kong "468" continuous-contract test (no frappe import;
tests/test_continuous.py).

An employee counts as continuously employed once they work at least 68 hours in any 4
consecutive weeks (the "468" rule; the old "418" rule was 18 hours in each week). Here the
test looks at the 28 days up to a given day. "Close" means 80 % of the way there, so managers
hear about it before it happens."""

from __future__ import annotations

from datetime import date, datetime, timedelta

WINDOW_DAYS = 28
THRESHOLD_HOURS = 68.0
WARN_FRACTION = 0.8

BELOW, CLOSE, REACHED = "Below", "Close", "Reached"
_RANK = {BELOW: 0, CLOSE: 1, REACHED: 2}


def shift_hours(checkins: list[tuple[str, datetime]]) -> dict[date, float]:
	"""Hours per day from an employee's Employee Checkin rows (log_type, time), oldest first.
	Each IN is closed by the next OUT; an IN with no OUT yet (still on shift) adds nothing."""
	out: dict[date, float] = {}
	start = None
	for log_type, when in sorted(checkins, key=lambda c: c[1]):
		if log_type == "IN":
			start = when
		elif log_type == "OUT" and start is not None:
			hours = (when - start).total_seconds() / 3600
			if hours > 0:
				out[start.date()] = out.get(start.date(), 0.0) + hours
			start = None
	return out


def window_hours(day_hours: dict[date, float], end: date, days: int = WINDOW_DAYS) -> float:
	first = end - timedelta(days=days - 1)
	return round(sum(h for d, h in day_hours.items() if first <= d <= end), 2)


def level(hours: float) -> str:
	if hours >= THRESHOLD_HOURS:
		return REACHED
	if round(hours, 2) >= round(THRESHOLD_HOURS * WARN_FRACTION, 2):
		return CLOSE
	return BELOW


def worsened(old: str | None, new: str) -> bool:
	"""True when the status moved up (Below to Close, Close to Reached), so one alert goes out
	per step and not one every day."""
	return _RANK.get(new, 0) > _RANK.get(old or BELOW, 0)


def hours_left(hours: float) -> float:
	return round(max(THRESHOLD_HOURS - hours, 0.0), 2)


def message(name: str, hours: float, status: str) -> str:
	if status == REACHED:
		return (f"{name} has worked {hours:g} hours in the last 4 weeks (68 needed): "
		        "now counts as continuously employed (rest days, holidays, sick pay, annual leave).")
	return (f"{name} has worked {hours:g} of 68 hours in the last 4 weeks, {hours_left(hours):g} hours "
	        "to go before counting as continuously employed.")
