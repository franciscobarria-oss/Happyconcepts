"""Pure helpers for replacing one ingredient by another across recipes
(replace_ingredient.py); unit-tested in tests/test_swap.py."""

from __future__ import annotations


def new_qty(qty, factor) -> float:
	return round(float(qty or 0) * float(factor or 1), 6)


def plan_swap(lines: list[dict], old: str, new: str, factor: float = 1.0) -> list[tuple]:
	"""What to do with a recipe's ingredient lines to use `new` instead of `old`.

	lines: [{"item", "qty", "uom", "yield_pct"}] in recipe order.
	Returns [("replace", i, qty)] to switch line i to the new item, or
	[("merge", i, j, qty)] to add line i's quantity to line j (which already uses
	the new item in the same unit and yield) and drop line i.
	"""
	if not old or not new or old == new:
		return []
	actions = []
	for i, line in enumerate(lines):
		if line.get("item") != old:
			continue
		qty = new_qty(line.get("qty"), factor)
		j = next(
			(
				j
				for j, other in enumerate(lines)
				if other.get("item") == new
				and other.get("uom") == line.get("uom")
				and float(other.get("yield_pct") or 100) == float(line.get("yield_pct") or 100)
			),
			None,
		)
		actions.append(("merge", i, j, qty) if j is not None else ("replace", i, qty))
	return actions
