"""Fill Item.hk_item_name_zh from the team's hand-made Daily Sales Overview sheet. Idempotent:
only blank fields are filled, nothing is overwritten. Dry run by default.

On the server, in the hcl-erp backend container (copy chinese_names.json to /tmp first):
    bench --site <site> console
    exec(open("/tmp/load_chinese_names.py").read(), globals()); run("/tmp/chinese_names.json")            # dry run
    exec(open("/tmp/load_chinese_names.py").read(), globals()); run("/tmp/chinese_names.json", apply=True)
"""
import json

import frappe


def _find(code):
	"""Item for a sheet code: the item itself, else the item holding that customer code (Customer Items),
	else the item a Sales Order line with that customer item code was entered under."""
	if frappe.db.exists("Item", code):
		return [code]
	out = set(frappe.get_all("Item Customer Detail", filters={"ref_code": code, "parenttype": "Item"}, pluck="parent"))
	out |= set(frappe.get_all("Sales Order Item", filters={"customer_item_code": code}, pluck="item_code"))
	return sorted(out)


def run(path, apply=False):
	names = json.load(open(path, encoding="utf-8"))
	done, same, unmatched, clash = [], [], [], []
	for code, zh in names.items():
		items = _find(code)
		if not items:
			unmatched.append(code)
			continue
		for item in items:
			cur = frappe.db.get_value("Item", item, "hk_item_name_zh")
			if not cur:
				done.append((code, item, zh))
				if apply:
					frappe.db.set_value("Item", item, "hk_item_name_zh", zh, update_modified=False)
			elif cur == zh:
				same.append(item)
			else:
				clash.append((code, item, cur, zh))
	if apply:
		frappe.db.commit()
	print("APPLIED" if apply else "DRY RUN", "| to fill:", len(done), "| already set:", len(same),
	      "| differs (left alone):", len(clash), "| no item found:", len(unmatched))
	for r in done:
		print("  fill", r)
	for r in clash:
		print("  differs", r)
	print("  no item:", unmatched)
