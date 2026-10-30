"""Fill Item shelf life (days) and the Customer sheet fields (heading, column name, Chinese location,
order) from the team's hand-made Daily Sales Overview sheet (sheet_reference.json). Idempotent: only
blank fields are filled, nothing is overwritten. Dry run by default.

On the server, in the hcl-erp backend container (copy both files to /tmp first):
    bench --site <site> console
    exec(open("/tmp/load_sheet_reference.py").read(), globals()); run("/tmp/sheet_reference.json")
    exec(open("/tmp/load_sheet_reference.py").read(), globals()); run("/tmp/sheet_reference.json", apply=True)
"""
import json

import frappe

# sheet heading + column name -> Customer name in hcl-erp (Xero names)
CUSTOMER_NAME = {
	("IKEA", None): "THE DAIRY FARM COMPANY LIMITED - {label}",
	("PPL", None): "PLAZA PREMIUM LOUNGE HKG - {label}",
	("SODEXO", "UA"): "SODEXO - UNITED AIRLINES",
	("SODEXO", "SA"): "SODEXO - SINGAPORE AIRLINE",
	("SODEXO", "Qantas"): "SODEXO - QANTAS AIRWAYS",
	("W Hotel", None): "W HOTEL",
}


def _customer(col):
	pattern = CUSTOMER_NAME.get((col["group"], col["label"])) or CUSTOMER_NAME.get((col["group"], None))
	if not pattern:
		return None
	name = pattern.format(label=col["label"])
	return frappe.db.get_value("Customer", {"customer_name": name}, "name")


def _items(code):
	"""Item for a sheet code: the item itself, else the item holding that customer code, else the item a
	Sales Order line with that customer item code was entered under."""
	if frappe.db.exists("Item", code):
		return [code]
	out = set(frappe.get_all("Item Customer Detail", filters={"ref_code": code, "parenttype": "Item"}, pluck="parent"))
	out |= set(frappe.get_all("Sales Order Item", filters={"customer_item_code": code}, pluck="item_code"))
	return sorted(out)


def run(path, apply=False):
	ref = json.load(open(path, encoding="utf-8"))
	rows = []  # (kind, name, field, value)
	skipped = []
	for code, days in ref["shelf_life_days"].items():
		items = _items(code)
		if not items:
			skipped.append(("item", code))
		for item in items:
			if not frappe.db.get_value("Item", item, "shelf_life_in_days"):
				rows.append(("Item", item, "shelf_life_in_days", days))
	for col in ref["columns"]:
		cust = _customer(col)
		if not cust:
			skipped.append(("customer", f'{col["group"]} / {col["label"]}'))
			continue
		for field, value in (("hk_sheet_group", col["group"]), ("hk_sheet_label", col["label"]),
		                     ("hk_sheet_label_zh", col["zh"]), ("hk_sheet_sort", col["sort"])):
			if value in (None, "") or frappe.db.get_value("Customer", cust, field) not in (None, "", 0):
				continue
			rows.append(("Customer", cust, field, value))
	for dt, name, field, value in rows:
		if apply:
			frappe.db.set_value(dt, name, field, value, update_modified=False)
	if apply:
		frappe.db.commit()
	print("APPLIED" if apply else "DRY RUN", "| to fill:", len(rows), "| not found:", len(skipped))
	for r in rows:
		print("  fill", r)
	print("  not found:", skipped)
