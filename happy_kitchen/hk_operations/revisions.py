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
