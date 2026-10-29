"""Sales Order stage for staff: Draft -> Confirmed -> Completed, and the one next step.

Built only on ERPNext's own fields (docstatus, status, per_delivered, per_billed), so nothing new
is stored. Confirmed = submitted; Completed = everything delivered, or closed (Complete while stock isn't
tracked closes the order instead of making a Delivery Note). Pure Python (no frappe):
public/js/sales_order.js and sales_order_list.js mirror these rules. Tests: tests/test_order_stage.py."""

from __future__ import annotations

from datetime import date

STEPS = ("Draft", "Confirmed", "Completed")


def _day(d) -> date | None:
	if not d:
		return None
	if isinstance(d, date):
		return d
	return date.fromisoformat(str(d)[:10])


def stage(docstatus: int, status: str | None = None, per_delivered: float = 0, per_billed: float = 0,
          delivery_date=None, today=None) -> dict:
	"""{stage, color, late, next} for an order. stage is Draft / Confirmed / Completed, or
	Cancelled / On Hold (ERPNext's own states, kept as they are). next is
	"confirm" (submit), "deliver" (Delivery Note) or None."""
	docstatus = int(docstatus or 0)
	per_delivered = float(per_delivered or 0)
	if docstatus == 0:
		return {"stage": "Draft", "color": "gray", "late": False, "next": "confirm"}
	if docstatus == 2:
		return {"stage": "Cancelled", "color": "red", "late": False, "next": None}
	if per_delivered >= 100 or status in ("Completed", "Closed"):
		# Closed = completed without a full Delivery Note (Complete while stock isn't tracked)
		return {"stage": "Completed", "color": "green", "late": False, "next": None,
		        "invoiced": float(per_billed or 0) >= 100, "no_delivery_note": per_delivered < 100}
	if status == "On Hold":
		return {"stage": status, "color": "orange", "late": False, "next": None}
	dd, td = _day(delivery_date), _day(today)
	late = bool(dd and td and dd < td)
	return {"stage": "Confirmed", "color": "red" if late else "blue", "late": late, "next": "deliver",
	        "part_delivered": per_delivered > 0}


def deliver_blocker(docstatus: int, status: str | None, per_delivered: float, needs_review: int = 0) -> str | None:
	"""Why "Mark as delivered" can't run now, or None."""
	if int(docstatus or 0) != 1:
		return "Only a confirmed order can be marked as delivered."
	if status == "On Hold":
		return "This order is on hold. Take it off hold first."
	if float(per_delivered or 0) >= 100 or status in ("Completed", "Closed"):
		return "This order is already completed."
	if int(needs_review or 0):
		return "This order was revised. Mark the revision as checked before delivering."
	return None
