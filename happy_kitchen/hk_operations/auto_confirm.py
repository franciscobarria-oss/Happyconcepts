"""When may a draft order from email be confirmed without a person (pure, tests/test_auto_confirm.py).

Recipe Settings `auto_confirm_email_orders` (off by default) confirms new draft Sales Orders made from
email. A person still looks at an order when it has no value, has a line with no price, or looks like a
copy of an order we already have (same customer, delivery date and total)."""

from __future__ import annotations

ZERO_VALUE = "No value"
NO_PRICE = "A line has no price"
DUPLICATE = "Looks like a duplicate"


def _num(v) -> float:
	try:
		return float(v or 0)
	except (TypeError, ValueError):
		return 0.0


def hold_reason(total, rates, duplicate: bool, is_sample: bool = False) -> str:
	"""'' when the order can be confirmed automatically, else why a person must check it.
	A sample order (Sales Order `hk_is_sample`) is kept at no value on purpose, so only a duplicate holds it."""
	if is_sample:
		return DUPLICATE if duplicate else ""
	if _num(total) <= 0:
		return ZERO_VALUE
	if any(_num(r) <= 0 for r in rates):
		return NO_PRICE
	if duplicate:
		return DUPLICATE
	return ""
