"""Checking a delivery against its purchase order (pure, unit-tested in
tests/test_receiving.py). The Receive Delivery screen and kitchen.receive_po
use it to flag lines in orange before stock is received."""

from __future__ import annotations

DEFAULT_PRICE_TOLERANCE_PCT = 0.5


def flt(value) -> float:
	try:
		return float(value or 0)
	except (TypeError, ValueError):
		return 0.0


def line_flags(ordered_qty, received_qty, po_rate, invoice_rate=None, price_tolerance_pct=DEFAULT_PRICE_TOLERANCE_PCT) -> list[str]:
	"""What's different about one delivered line. Quantities in the PO unit,
	prices per PO unit. invoice_rate None/0 = price not checked."""
	flags = []
	ordered, received = flt(ordered_qty), flt(received_qty)
	if received <= 0 < ordered:
		flags.append("not delivered")
	elif received < ordered - 1e-9:
		flags.append(f"short {ordered - received:g}")
	elif received > ordered + 1e-9:
		flags.append(f"over {received - ordered:g}")
	if flt(invoice_rate) and flt(po_rate):
		diff_pct = (flt(invoice_rate) - flt(po_rate)) / flt(po_rate) * 100.0
		if abs(diff_pct) > price_tolerance_pct:
			flags.append(f"price {'+' if diff_pct > 0 else ''}{diff_pct:.1f}%")
	elif flt(invoice_rate) and not flt(po_rate):
		flags.append("price not on order")
	return flags


def delivery_summary(lines: list[dict], price_tolerance_pct=DEFAULT_PRICE_TOLERANCE_PCT) -> dict:
	"""lines: [{item, ordered_qty, received_qty, po_rate, invoice_rate}]
	Returns per-line flags, the received value and whether anything needs a look."""
	out, total, flagged = [], 0.0, 0
	for l in lines:
		f = line_flags(l.get("ordered_qty"), l.get("received_qty"), l.get("po_rate"), l.get("invoice_rate"), price_tolerance_pct)
		total += flt(l.get("received_qty")) * flt(l.get("po_rate"))  # received at the ordered price
		flagged += 1 if f else 0
		out.append({"item": l.get("item"), "flags": f})
	return {"lines": out, "received_value": total, "flagged_lines": flagged, "has_discrepancy": flagged > 0}
