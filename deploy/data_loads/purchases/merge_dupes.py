"""Merge duplicate new items on hcl-erp (survivor keeps its code). dry_run rolls back."""
import frappe
from frappe.model.rename_doc import rename_doc

GRAMS_PER_EGG = 50  # old prices: 0.8333/each vs 0.016667/g
# dup -> survivor
PAIRS = {"ING-605": "ING-539", "ING-596": "ING-595", "ING-577": "ING-547"}
GRAM_UNIT_FOR = {"ING-595"}
RENAME = {"ING-547": "Twinings Earl Grey Tea Bags"}  # keep the more specific name
NOTES = {"ING-547": "Old price note: ING-141 had 0.74 per GRAM in the old system (wrong unit); use 0.74 per bag (ING-054, Ongo)."}  # eggs only; tea bags have no useful gram weight

def run(dry_run=True):
	try:
		for dup, keep in PAIRS.items():
			d = frappe.get_doc("Item", dup); k = frappe.get_doc("Item", keep)
			old = [l for l in (d.description or "").split("<br>") if l.startswith("Old code:")]
			if d.stock_uom != k.stock_uom:
				# dup has no stock/transactions, so its unit can be aligned before the merge
				frappe.db.set_value("Item", dup, "stock_uom", k.stock_uom)
				frappe.db.sql("update `tabUOM Conversion Detail` set uom=%s where parent=%s and conversion_factor=1", (k.stock_uom, dup))
				if keep in GRAM_UNIT_FOR and d.stock_uom == "Gram" and not any(u.uom == "Gram" for u in k.uoms):
					k.append("uoms", {"uom": "Gram", "conversion_factor": 1.0 / GRAMS_PER_EGG})
			k.description = (k.description or "") + "".join(f"<br>{o} - merged from {dup} {d.item_name}" for o in old)
			if keep in RENAME:
				k.item_name = RENAME[keep]
			if keep in NOTES:
				k.description += "<br>" + NOTES[keep]
			k.save(ignore_permissions=True)
			rename_doc("Item", dup, keep, merge=True, ignore_permissions=True)
			k = frappe.get_doc("Item", keep)
			print(dup, d.item_name, "->", keep, k.item_name, "| dup exists after:", bool(frappe.db.exists("Item", dup)),
				"| uoms:", [(u.uom, round(u.conversion_factor, 4)) for u in k.uoms], "| desc:", k.description)
	finally:
		if dry_run:
			frappe.db.rollback(); print("DRY RUN - rolled back")
	if not dry_run:
		frappe.db.commit(); print("COMMITTED")
