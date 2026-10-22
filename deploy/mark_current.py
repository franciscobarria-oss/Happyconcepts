"""Mark the last-purchased version of repeated items as CURRENT. Idempotent.
Repeated = same item name across item codes (e.g. Tomato kg / tin), or one item code bought from several suppliers.
Writes: Item Price.note ("CURRENT ..." / "Older ...") and the first description line on each Item.
Usage (bench console): exec(open('/tmp/mark_current.py').read()); run('/tmp/purchase_master.json', dry_run=True)"""
import json, re
import frappe


def run(path, dry_run=True):
	data = json.load(open(path))
	groups = {}
	for it in data["items"]:
		groups.setdefault(it["item_name"].strip().lower(), []).append(it)
	n_cur = n_old = 0
	for rows in groups.values():
		repeated = len({r["item_code"] for r in rows}) > 1 or len({r["supplier"] for r in rows}) > 1
		if not repeated or not any(r["last_date"] for r in rows):
			continue
		cur = max(rows, key=lambda r: r["last_date"] or "")
		for r in rows:
			is_cur = r is cur
			tag = (f"CURRENT - last purchased {r['last_date']} ({r['supplier']})" if is_cur
			       else f"Older - last purchased {r['last_date']}; current is {cur['item_code']} ({cur['supplier']}, {cur['last_date']})")
			sid = frappe.db.get_value("Supplier", {"supplier_name": r["supplier"][:140]}, "name")
			for ip in frappe.get_all("Item Price", filters={"item_code": r["item_code"], "supplier": sid, "buying": 1}, pluck="name"):
				old = frappe.db.get_value("Item Price", ip, "note") or ""
				base = re.sub(r"^(CURRENT|Older)[^|]*\|\s*", "", old)
				frappe.db.set_value("Item Price", ip, "note", f"{tag} | {base}"[:140])
			desc = frappe.db.get_value("Item", r["item_code"], "description") or ""
			desc = re.sub(r"^(CURRENT|Older)[^\n]*\n", "", desc)
			if frappe.db.exists("Item", r["item_code"]):
				frappe.db.set_value("Item", r["item_code"], "description", f"{tag}\n{desc}")
			n_cur += is_cur
			n_old += not is_cur
	print("current:", n_cur, "older:", n_old)
	if dry_run:
		frappe.db.rollback(); print("DRY RUN")
	else:
		frappe.db.commit(); print("committed")
