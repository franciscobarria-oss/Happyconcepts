"""Plain-Python rules and setup data for the Team pages (no frappe import; tests/test_team.py).

Hong Kong specifics: employer MPF 5 %, capped at HK$1,500 a month; Employment Ordinance
annual leave scale; Labour Department statutory holidays."""

from __future__ import annotations

import hashlib
from datetime import date

MPF_RATE = 0.05
MPF_CAP = 1500.0

# Roster cell cycle: empty -> Early -> Late -> empty
SHIFTS = ("Early", "Late")
# name: (start, end, calendar colour)
SHIFT_TYPES = {
	"Early": ("07:00:00", "16:00:00", "Blue"),
	"Late": ("11:00:00", "20:00:00", "Violet"),
}
LATE_GRACE_MIN = 10

DEPARTMENTS = ["Sweet", "Savoury", "General", "Central Kitchen"]

LABOUR_ACTIVITY = "Kitchen Labour"
OVERTIME_ACTIVITY = "Overtime"
OVERTIME_ACTIVITY_RATE = 84.0  # HK$80 standard overtime + 5 % MPF

ANNUAL_LEAVE = "Annual Leave"

# name, method, value (methods as in hk_operations.calc)
OVERTIME_RATES = [
	("Standard HK$80", "Fixed per hour", 80),
	("Time and a half", "Multiple of own hourly wage", 1.5),
	("Double time", "Multiple of own hourly wage", 2.0),
]

TABLET_ROLE = "Kitchen Tablet"
MANAGER_ROLES = ["System Manager", "HR Manager"]
LEAVE_APPROVER = "francisco.barria@gmail.com"

# Labour Department statutory holidays (Christmas Day chosen over the Winter Solstice).
HOLIDAY_LIST = "HK Statutory 2026-27"
HOLIDAY_LIST_RANGE = ("2026-01-01", "2027-12-31")
HOLIDAYS = {
	"2026-01-01": "The first day of January", "2026-02-17": "Lunar New Year's Day",
	"2026-02-18": "The second day of Lunar New Year", "2026-02-19": "The third day of Lunar New Year",
	"2026-04-05": "Ching Ming Festival", "2026-04-06": "Easter Monday", "2026-05-01": "Labour Day",
	"2026-05-24": "The Birthday of the Buddha", "2026-06-19": "Tuen Ng Festival",
	"2026-07-01": "HKSAR Establishment Day", "2026-09-26": "The day following Mid-Autumn Festival",
	"2026-10-01": "National Day", "2026-10-18": "Chung Yeung Festival", "2026-12-25": "Christmas Day",
	"2026-12-26": "The first weekday after Christmas Day",
	"2027-01-01": "The first day of January", "2027-02-06": "Lunar New Year's Day",
	"2027-02-08": "The third day of Lunar New Year", "2027-02-09": "The fourth day of Lunar New Year",
	"2027-03-29": "Easter Monday", "2027-04-05": "Ching Ming Festival", "2027-05-01": "Labour Day",
	"2027-05-13": "The Birthday of the Buddha", "2027-06-09": "Tuen Ng Festival",
	"2027-07-01": "HKSAR Establishment Day", "2027-09-16": "The day following Mid-Autumn Festival",
	"2027-10-01": "National Day", "2027-10-08": "Chung Yeung Festival", "2027-12-25": "Christmas Day",
	"2027-12-27": "The first weekday after Christmas Day",
}


def flt(value) -> float:
	try:
		return float(value or 0)
	except (TypeError, ValueError):
		return 0.0


def hourly_cost(monthly_base=0, working_days=0, hours_per_day=0, hourly_rate=0) -> float:
	"""Employer cost per hour: hourly wage x 1.05, or (monthly base + MPF 5 % capped at 1,500)
	/ (days x hours). 0 when the pay fields are incomplete."""
	if flt(hourly_rate) > 0:
		return round(flt(hourly_rate) * (1 + MPF_RATE), 2)
	base, days, hours = flt(monthly_base), flt(working_days), flt(hours_per_day)
	if base > 0 and days > 0 and hours > 0:
		return round((base + min(base * MPF_RATE, MPF_CAP)) / (days * hours), 2)
	return 0.0


def shift_hours(start: str, end: str) -> float:
	"""Hours between two "HH:MM[:SS]" times on the same day (the roster's planned hours)."""
	def mins(t):
		h, m = t.split(":")[:2]
		return int(h) * 60 + int(m)
	return (mins(end) - mins(start)) / 60


def valid_pin(pin) -> bool:
	return isinstance(pin, str) and len(pin) == 4 and pin.isdigit()


def pin_hash(employee: str, pin: str) -> str:
	"""SHA-256 of "<employee id>:<pin>"; only the hash is stored."""
	return hashlib.sha256(f"{employee}:{pin}".encode()).hexdigest()


def next_shift(current: str | None) -> str | None:
	"""Roster tap: Off -> Early -> Late -> Off (an unknown shift goes back to Off)."""
	if not current:
		return SHIFTS[0]
	if current not in SHIFTS:
		return None
	i = SHIFTS.index(current) + 1
	return SHIFTS[i] if i < len(SHIFTS) else None


def next_log_type(last_log_type: str | None) -> str:
	"""Clock-in kiosk: IN unless the last check-in today was IN."""
	return "OUT" if last_log_type == "IN" else "IN"


def annual_leave_days(joined: date, on: date) -> int:
	"""Employment Ordinance scale: 0 in the first year, 7 days for years 1-2, then +1 a year
	up to 14."""
	years = (on.year - joined.year) - ((on.month, on.day) < (joined.month, joined.day))
	if years < 1:
		return 0
	return 7 if years <= 2 else min(14, years + 5)
