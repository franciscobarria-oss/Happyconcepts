"""Plain-Python rules for HK Operations (overtime pay, price checks, food cost).
No Frappe imports, so tests/test_hk_operations.py runs anywhere."""

from __future__ import annotations

FIXED = "Fixed per hour"
MULTIPLE = "Multiple of own hourly wage"


def flt(value) -> float:
	try:
		return float(value or 0)
	except (TypeError, ValueError):
		return 0.0


def own_hourly_wage(monthly_base=0, working_days=0, hours_per_day=0, hourly_rate=0) -> float:
	"""The employee's own hourly wage, from the Employee HK fields: the hourly
	rate for hourly staff, otherwise monthly base / (working days x hours per day).
	Employer MPF is not part of the wage."""
	if flt(hourly_rate) > 0:
		return flt(hourly_rate)
	if flt(monthly_base) <= 0 or flt(working_days) <= 0 or flt(hours_per_day) <= 0:
		return 0.0
	return flt(monthly_base) / (flt(working_days) * flt(hours_per_day))


def overtime_hourly_amount(method, value, wage=0.0) -> float:
	"""HK$ per overtime hour. Fixed: the rate itself. Multiple: own wage x value
	(not rounded, so 3.5 h x 20,000/216 x 1.5 comes to HK$ 486.11)."""
	if method == FIXED:
		return round(flt(value), 2)
	if method == MULTIPLE:
		return flt(wage) * flt(value)
	raise ValueError(f"Unknown overtime method: {method!r}")


def overtime_amount(hours, hourly_amount) -> float:
	return round(flt(hours) * flt(hourly_amount), 2)


def pct_change(new, old) -> float | None:
	"""% change from old to new, None when there is nothing to compare."""
	if not flt(old) or not flt(new):
		return None
	return (flt(new) - flt(old)) / flt(old) * 100.0


# status codes from food_cost_check -> tone (the report turns codes into translated text)
FOOD_COST_TONES = {
	"missing_prices": "warning",
	"no_price": "warning",
	"over": "danger",
	"just_over": "warning",
	"on_target": "success",
	"": "",
}


def food_cost_check(cost_per_unit, selling_price, target_pct, missing_prices=0) -> tuple[float | None, str, str]:
	"""(food cost %, status code, tone) for one recipe. Tone is success / warning / danger / ''.
	"Just over" is within 5 points of the target."""
	if int(missing_prices or 0) > 0:
		pct = flt(cost_per_unit) / flt(selling_price) * 100.0 if flt(selling_price) else None
		code = "missing_prices"
	elif not flt(selling_price):
		pct, code = None, "no_price"
	else:
		pct = flt(cost_per_unit) / flt(selling_price) * 100.0
		target = flt(target_pct)
		if not target:
			code = ""
		elif pct > target + 5:
			code = "over"
		elif pct > target:
			code = "just_over"
		else:
			code = "on_target"
	return pct, code, FOOD_COST_TONES[code]
