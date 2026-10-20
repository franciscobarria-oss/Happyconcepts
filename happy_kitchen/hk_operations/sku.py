"""Pure supplier-SKU rules (no Frappe import; tests/test_sku.py).

Our own SKU is the Item code. A supplier's SKU is the part number on the Item's
"Supplier Items" row for that supplier (Item Supplier.supplier_part_no)."""

from __future__ import annotations


def clean(sku) -> str:
	return (sku or "").strip()


def search_text(rows) -> str:
	"""Item.hk_supplier_skus: every supplier SKU on the item, for the Item search."""
	seen: list[str] = []
	for r in rows:
		sku = clean(r.get("supplier_part_no"))
		if sku and sku not in seen:
			seen.append(sku)
	return ", ".join(seen)


def repeated_in_item(rows) -> tuple[str, str] | None:
	"""(supplier, sku) when one supplier's SKU appears twice on the same item, else None."""
	seen = set()
	for r in rows:
		sku = clean(r.get("supplier_part_no"))
		if not sku:
			continue
		key = (r.get("supplier"), sku.lower())
		if key in seen:
			return r.get("supplier"), sku
		seen.add(key)
	return None


def sku_for_supplier(rows, supplier) -> str:
	"""The supplier's SKU for this item ('' when it has none)."""
	for r in rows:
		if r.get("supplier") == supplier and clean(r.get("supplier_part_no")):
			return clean(r.get("supplier_part_no"))
	return ""
