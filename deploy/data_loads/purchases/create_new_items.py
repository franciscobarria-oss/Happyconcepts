"""Create the ingredients marked NEW (approved_matches.json "new_items") on hcl-erp.

Inputs (copied to /tmp in the backend container):
  /tmp/approved_matches.json        - Francisco's choices, key "new_items"
  /tmp/old_new_items_source.json    - item_group / stock_uom / suppliers / Standard Buying prices
                                      read (read-only) from the old site erp.fbs-host.com
Run: bench --site hcl-erp.fbs-host.com console
     exec(open("/tmp/create_new_items.py").read()); run(dry_run=True)
Idempotent: an item whose item_name already exists is skipped (its code is still mapped).
"""
import json, re
import frappe

PRICE_LIST = "Standard Buying"
NOTE_RE = re.compile(r"\s*(?:-\s*|\()\s*(COST MISSING|SOURCE CHECK|SOURCE COMPONENT)\s*\)?\s*$", re.I)


def _supplier(name):
	if not name:
		return None
	if frappe.db.exists("Supplier", name):
		return name
	return frappe.db.get_value("Supplier", {"supplier_name": name}, "name")


def _next_code():
	rows = frappe.db.sql("select name from `tabItem` where name regexp '^ING-[0-9]+$'")
	return max([int(r[0][4:]) for r in rows] or [0]) + 1


def _pick(old):
	"""Old supplier name + the matching old price row (or None)."""
	notes = []
	sup = next((d["default_supplier"] for d in old["defaults"] if d["default_supplier"]), None) \
		or next((s["supplier"] for s in old["suppliers"] if s["supplier"]), None)
	prices = old["prices"]  # newest first
	if not sup:
		named = [p for p in prices if p["supplier"]]
		if named:
			sup = named[0]["supplier"]
			notes.append("supplier taken from old price row (no default supplier on old item)")
			if len({p["supplier"] for p in named}) > 1:
				notes.append("old item had prices from several suppliers: " + ", ".join(
					f"{p['supplier']} {p['price_list_rate']}" for p in named) + f" - used newest ({sup})")
	price = next((p for p in prices if p["supplier"] == sup), None)
	return sup, price, notes


def run(dry_run=True):
	company = frappe.defaults.get_global_default("company")
	rows = sorted(json.load(open("/tmp/approved_matches.json"))["new_items"], key=lambda r: r["old_code"])
	src = json.load(open("/tmp/old_new_items_source.json"))
	mapping, report = {}, []
	c = {"created": 0, "skipped_existing": 0, "failed": 0, "with_price": 0, "without_price": 0, "supplier_linked": 0}
	nxt = _next_code()
	for r in rows:
		old = src[r["old_code"]]
		raw = r["old_name"].strip()
		m = NOTE_RE.search(raw)
		name = NOTE_RE.sub("", raw).strip() if m else raw
		ex = frappe.db.get_value("Item", {"item_name": name}, "name") or frappe.db.get_value("Item", {"item_name": raw}, "name")
		if ex:
			mapping[r["old_code"]] = ex
			c["skipped_existing"] += 1
			report.append((r["old_code"], ex, name, "SKIPPED (name exists)", ""))
			continue
		code = f"ING-{nxt:03d}"
		while frappe.db.exists("Item", code):
			nxt += 1
			code = f"ING-{nxt:03d}"
		old_sup, price, notes = _pick(old)
		sid = _supplier(old_sup)
		if old_sup and not sid:
			notes.append(f"old supplier '{old_sup}' not on hcl-erp - not linked, no price")
		desc = [name]
		if m:
			desc.append(f"Old note: {m.group(1).upper()}")
		desc.append(f"Old code: {r['old_code']} (old system)")
		group = "Packaging" if (old["item_group"] or "").lower().startswith("packag") else "Ingredients"
		frappe.db.savepoint("ni")
		try:
			doc = frappe.get_doc({"doctype": "Item", "item_code": code, "item_name": name, "item_group": group,
				"stock_uom": old["stock_uom"], "is_stock_item": 1, "is_purchase_item": 1, "is_sales_item": 0,
				"description": "<br>".join(desc)})
			if sid:
				doc.append("supplier_items", {"supplier": sid})
				if company:
					doc.append("item_defaults", {"company": company, "default_supplier": sid})
			doc.insert(ignore_permissions=True)
			got_price = ""
			if sid and price and price["price_list_rate"]:
				frappe.get_doc({"doctype": "Item Price", "item_code": code, "price_list": PRICE_LIST, "supplier": sid,
					"buying": 1, "uom": old["stock_uom"], "currency": price["currency"] or "HKD",
					"price_list_rate": round(float(price["price_list_rate"]), 6)}).insert(ignore_permissions=True)
				got_price = price["price_list_rate"]
				c["with_price"] += 1
			else:
				c["without_price"] += 1
				if sid and not price:
					notes.append("no Standard Buying price on old item")
				elif not old_sup:
					notes.append("no supplier on old item" + (" (old price had no supplier)" if old["prices"] else ""))
			c["created"] += 1
			c["supplier_linked"] += 1 if sid else 0
			mapping[r["old_code"]] = code
			report.append((r["old_code"], code, name, f"{group}/{old['stock_uom']} sup={sid or '-'} price={got_price or '-'}", "; ".join(notes)))
			nxt += 1
		except Exception as e:
			frappe.db.rollback(save_point="ni")
			c["failed"] += 1
			report.append((r["old_code"], "-", name, "FAILED", repr(e)[:300]))
	for line in report:
		print(" | ".join(str(x) for x in line))
	print("COUNTS", json.dumps(c))
	print("MAPSTART" + json.dumps(mapping) + "MAPEND")
	if dry_run:
		frappe.db.rollback()
		print("DRY RUN - rolled back")
	else:
		frappe.db.commit()
		print("COMMITTED")
