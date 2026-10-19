"""What goes on the small kitchen date labels (P15b), as plain data so it can be
unit-tested; label_render.render_kitchen draws it. Bilingual: English, then 中文."""

from __future__ import annotations

from happy_kitchen.hk_operations import dates

OPENED, BATCH = "Opened", "Batch"
KINDS = ("Product", OPENED, BATCH)


def allergen_text(allergens: list[tuple[str, str]]) -> str:
	"""Contains 含: Gluten 麩質, Eggs 蛋"""
	if not allergens:
		return ""
	return "Contains 含: " + ", ".join(f"{en} {zh}".strip() for en, zh in allergens)


def kitchen_lines(c: dict) -> list[tuple[str, str]]:
	"""(style, text) lines, top to bottom. Styles: title, sub, row, big, small.

	c: kind (Opened / Batch), item_name, item_name_zh, start (opened at / made on),
	use_by, storage (Ambient / Chilled / Frozen), allergens [(en, zh)], by, lot."""
	out = [("title", c.get("item_name") or "")]
	zh = (c.get("item_name_zh") or "").strip()
	if zh and zh != (c.get("item_name") or "").strip():
		out.append(("sub", zh))
	if c.get("kind") == BATCH:
		if c.get("lot"):
			out.append(("row", f"BATCH 批次  {c['lot']}"))
		out.append(("row", f"MADE 製造  {dates.fmt_when(c.get('start'))}"))
	else:
		out.append(("row", f"OPENED 開封  {dates.fmt_when(c.get('start'))}"))
	out.append(("big", f"USE BY 此前使用  {dates.fmt_when(c.get('use_by')) or '-'}"))
	storage = c.get("storage")
	if storage:
		out.append(("row", f"{storage} {dates.STORAGE_ZH.get(storage, '')}".strip()))
	if c.get("allergens"):
		out.append(("small", allergen_text(c["allergens"])))
	tail = []
	if c.get("kind") != BATCH and c.get("lot"):
		tail.append(f"Batch 批次 {c['lot']}")
	if c.get("by"):
		tail.append(f"By 經手 {c['by']}")
	if tail:
		out.append(("small", "  ·  ".join(tail)))
	return out
