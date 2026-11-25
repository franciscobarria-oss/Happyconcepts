"""Pure order-revision rules (no Frappe import; tests/test_revisions.py).

A revision is a change to the items or quantities of an order. Lines are
[{"item_code", "qty"}]; the same item on two lines counts as one."""

from __future__ import annotations

EPS = 1e-9


def normalize(lines) -> dict[str, float]:
	"""{item_code: total qty}, lines without an item or with no quantity dropped."""
	out: dict[str, float] = {}
	for l in lines or []:
		code, qty = l.get("item_code"), float(l.get("qty") or 0)
		if code and qty > EPS:
			out[code] = out.get(code, 0.0) + qty
	return out


def changes(old, new) -> list[tuple[str, float, float]]:
	"""[(item_code, old qty, new qty)] for every item added, removed or changed (0 = not on the order)."""
	a, b = normalize(old), normalize(new)
	return [(c, a.get(c, 0.0), b.get(c, 0.0)) for c in sorted(set(a) | set(b)) if abs(a.get(c, 0.0) - b.get(c, 0.0)) > EPS]


def _n(v: float) -> str:
	return f"{v:g}"


def summary(diff, names: dict[str, str] | None = None) -> str:
	"""'Brownie: 12 → 18; Scone: removed (was 6); Cookie: added 24'."""
	names = names or {}
	parts = []
	for code, was, now in diff:
		label = names.get(code) or code
		if was <= EPS:
			parts.append(f"{label}: added {_n(now)}")
		elif now <= EPS:
			parts.append(f"{label}: removed (was {_n(was)})")
		else:
			parts.append(f"{label}: {_n(was)} → {_n(now)}")
	return "; ".join(parts)


# What to do when an email restates a PO that already has a Sales Order.
UNCHANGED, APPLY, MANUAL = "unchanged", "apply", "manual"


def po_action(diff, docstatus: int, status: str = "", per_delivered: float = 0, per_billing: float = 0):
	"""(action, reason) for a PO email that matches an existing order.

	unchanged: same items and quantities. apply: change the order itself (a draft, or a submitted order
	nothing has left yet). manual: the order is delivered, invoiced, closed or cancelled, so a person decides."""
	if not diff:
		return UNCHANGED, ""
	if docstatus == 2:
		return MANUAL, "the order is cancelled"
	if docstatus == 0:
		return APPLY, ""
	if (per_delivered or 0) > EPS:
		return MANUAL, "the order is already delivered"
	if (per_billing or 0) > EPS:
		return MANUAL, "the order is already invoiced"
	if status in ("Closed", "Completed"):
		return MANUAL, f"the order is {status.lower()}"
	return APPLY, ""


def keep_unmentioned(old_lines, new_lines):
	"""new_lines plus every item of old_lines the email does not mention, at its old quantity.
	An email never removes an item by leaving it out (it may list only what changed), and ERPNext's
	Update Items deletes any row missing from its payload, so the full list is always sent."""
	mentioned = {l.get("item_code") for l in new_lines or []}
	kept = [{"item_code": c, "qty": q} for c, q in normalize(
		[l for l in old_lines or [] if l.get("item_code") not in mentioned]).items()]
	return list(new_lines or []) + kept
