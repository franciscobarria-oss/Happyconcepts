"""Which confirmed email orders count as delivered without a person (pure, tests/test_auto_complete.py).

Recipe Settings `auto_complete_email_orders` (Francisco, 2026-11-17, "for the time being"): an order that
came from a readable email and was confirmed is assumed prepared and sent on its delivery date. It is
completed the day AFTER that date, so it still shows on Today and the production sheet on the day itself.
Orders that need a person (revised and not yet checked, on hold, already completed) are left alone."""

from __future__ import annotations

from happy_kitchen.hk_operations import order_stage


def is_due(docstatus, status, per_delivered, needs_review, delivery_date, today) -> bool:
	if order_stage.deliver_blocker(docstatus, status, per_delivered, needs_review):
		return False
	dd, td = order_stage._day(delivery_date), order_stage._day(today)
	return bool(dd and td and dd < td)
