"""Customer PO prices against our prices (pure, tested in tests/test_order_prices.py).

An order picked up from a customer's email or PDF can carry the customer's unit price. The draft
Sales Order first gets our own price (ERPNext's price list and pricing rules). Then, per line:
- we have no price and the PO has one -> the PO price is used ("PO price used");
- both have a price and they differ    -> our price stays, the line is flagged ("Price differs");
- both the same                        -> "Same price";
- neither has one                      -> "No price" (the line stays at 0 for a person to fill);
- only we have one                     -> "" (nothing to compare).
Nothing here blocks an order: the result is shown as a warning."""

from __future__ import annotations

TOLERANCE = 0.005  # half a cent per unit counts as the same price

USED = "PO price used"
DIFFERS = "Price differs"
SAME = "Same price"
NONE = "No price"
STATUSES = (USED, DIFFERS, SAME, NONE)


def _num(v) -> float:
	try:
		return float(v or 0)
	except (TypeError, ValueError):
		return 0.0


def parse_price(text) -> float:
	"""'1,234.50' / 'HK$ 12.00' / '12' -> the number; anything else -> 0."""
	import re

	m = re.search(r"\d[\d,]*(?:\.\d+)?", str(text or ""))
	if not m:
		return 0.0
	try:
		return float(m.group().replace(",", ""))
	except ValueError:
		return 0.0


def check(po_rate, our_rate) -> dict:
	"""{"status", "rate": the rate the order line should have, "fill": True when the PO price fills a
	missing price, "diff": PO minus ours, "pct": that as % of ours}."""
	po, ours = _num(po_rate), _num(our_rate)
	out = {"status": "", "rate": ours, "fill": False, "diff": 0.0, "pct": 0.0}
	if po <= 0:
		out["status"] = NONE if ours <= 0 else ""
		return out
	if ours <= 0:
		out.update(status=USED, rate=po, fill=True)
		return out
	diff = round(po - ours, 4)
	if abs(diff) < TOLERANCE:
		out["status"] = SAME
		return out
	out.update(status=DIFFERS, diff=diff, pct=round(diff / ours * 100, 1))
	return out


def differs(po_rate, rate) -> bool:
	"""A line whose PO price and order price are not the same (both set). Mirrored in sales_order.js."""
	po, r = _num(po_rate), _num(rate)
	return po > 0 and r > 0 and abs(po - r) >= TOLERANCE


def money(v) -> str:
	"""12 -> '12.00', 0.125 -> '0.125' (prices per gram keep up to 4 decimals)."""
	s = f"{_num(v):,.4f}".rstrip("0")
	whole, _, dec = s.partition(".")
	return f"{whole}.{dec.ljust(2, '0')}"


def signed(result: dict) -> str:
	"""'+1.50, +12.5%' / '−1.50, −10.0%' for a "Price differs" result (PO price minus ours)."""
	sign = "+" if result["diff"] > 0 else "−"
	return f"{sign}{money(abs(result['diff']))}, {sign}{abs(result['pct'])}%"


def counts(statuses) -> dict:
	"""How many lines per status (only the four statuses)."""
	out = {s: 0 for s in STATUSES}
	for s in statuses:
		if s in out:
			out[s] += 1
	return out
