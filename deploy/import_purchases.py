"""One-off, idempotent load of suppliers + purchase items from a purchase_master.json
(built from the Ingredients_<month>_2026 workbooks).

Run inside the backend container (copy both files to /tmp first):
    bench --site <site> console   then:
        exec(open("/tmp/import_purchases.py").read()); run("/tmp/purchase_master.json", dry_run=True)
    (dry_run=True rolls back; use dry_run=False to commit.)

Re-running is safe: suppliers and items are matched by name/code, prices are updated in place.
"""
import json
import re

import frappe

PRICE_LIST = "Standard Buying"
CNY_PRICE_LIST = "Taobao Buying (CNY)"
GROUPS = {"Trade Supplier": "Trade Supplier", "Retail": "Retail", "Online (Taobao)": "Online (Taobao)"}


def _ensure(doctype, name, **vals):
	if frappe.db.exists(doctype, name):
		return name
	doc = frappe.get_doc({"doctype": doctype, **vals})
	doc.insert(ignore_permissions=True)
	return doc.name


def _prep():
	root = frappe.db.get_value("Supplier Group", {"is_group": 1, "parent_supplier_group": ""}, "name") or "All Supplier Groups"
	for g in GROUPS.values():
		_ensure("Supplier Group", g, supplier_group_name=g, parent_supplier_group=root)
	if frappe.db.exists("Currency", "CNY"):
		frappe.db.set_value("Currency", "CNY", "enabled", 1)
	_ensure("Price List", CNY_PRICE_LIST, price_list_name=CNY_PRICE_LIST, currency="CNY", buying=1, selling=0, enabled=1)
	return root


def _uom(name):
	if not frappe.db.exists("UOM", name):
		frappe.get_doc({"doctype": "UOM", "uom_name": name, "must_be_whole_number": 1}).insert(ignore_permissions=True)


def _clean_email(s):
	for part in re.split(r"[;,/ ]+", s or ""):
		if re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", part):
			return part
	return ""


def load_suppliers(data, dry_run):
	created = updated = 0
	for s in data["suppliers"]:
		name = s["name"][:140]
		details = []
		for label, key in (("Payment terms", "payment_terms"), ("Delivery minimum", "moq"), ("Contact", "contact"),
		                   ("Phone", "phone"), ("Email", "email"), ("Address", "address")):
			if s.get(key):
				details.append(f"{label}: {s[key]}")
		details.append(f"Seen on invoices {s['first']} to {s['last']} ({s['invoices']} invoices), loaded from purchase workbooks Jun-Sep 2026.")
		vals = {"supplier_group": GROUPS[s["group"]], "supplier_type": "Company", "default_currency": s["currency"],
		        "supplier_details": "\n".join(details), "website": (s.get("website") or "")[:140]}
		existing = frappe.db.get_value("Supplier", {"supplier_name": name}, "name")
		if existing:
			updated += 1
			if not dry_run:
				doc = frappe.get_doc("Supplier", existing)
				for k, v in vals.items():
					if v and not doc.get(k):
						doc.set(k, v)
				doc.save(ignore_permissions=True)
		else:
			created += 1
			if not dry_run:
				doc = frappe.get_doc({"doctype": "Supplier", "supplier_name": name, **vals}).insert(ignore_permissions=True)
				existing = doc.name
		if dry_run:
			continue
		link = {"link_doctype": "Supplier", "link_name": existing}
		if s.get("address") and not frappe.db.exists("Dynamic Link", {"link_doctype": "Supplier", "link_name": existing, "parenttype": "Address"}):
			frappe.get_doc({"doctype": "Address", "address_title": name[:100], "address_type": "Billing",
			                "address_line1": s["address"][:140], "city": "Hong Kong" if s["currency"] == "HKD" else "-",
			                "country": "Hong Kong" if s["currency"] == "HKD" else "China",
			                "phone": (s.get("phone") or "")[:140], "email_id": _clean_email(s.get("email")),
			                "links": [link]}).insert(ignore_permissions=True)
		if (s.get("contact") or s.get("phone") or s.get("email")) and not frappe.db.exists(
				"Dynamic Link", {"link_doctype": "Supplier", "link_name": existing, "parenttype": "Contact"}):
			c = {"doctype": "Contact", "first_name": (s.get("contact") or name)[:140], "links": [link]}
			if _clean_email(s.get("email")):
				c["email_ids"] = [{"email_id": _clean_email(s["email"]), "is_primary": 1}]
			if s.get("phone"):
				c["phone_nos"] = [{"phone": s["phone"][:140], "is_primary_phone": 1}]
			frappe.get_doc(c).insert(ignore_permissions=True)
	return created, updated


def load_items(data, dry_run):
	company = frappe.defaults.get_global_default("company")
	by_code = {}
	for it in data["items"]:
		by_code.setdefault(it["item_code"], []).append(it)
	names_used = {}
	created = priced = skipped = 0
	for code, rows in by_code.items():
		first = rows[0]
		base = first["item_name"].strip()[:130]
		suffix = ""
		if base.lower() in names_used and names_used[base.lower()] != code:
			suffix = f" ({first['purchase_uom']})"
		names_used[base.lower()] = code
		item_name = base + suffix
		group = "Packaging" if first["category"] == "packaging" else "Ingredients"
		desc = [first["presentation"] and f"Pack: {first['presentation']}", f"Bought per {first['purchase_uom']} = {first['size_basis']}"]
		for r in rows:
			desc.append(f"[{r['supplier']}] {r['price_note']}" if r["price_note"] else "")
			if r["flags"]:
				desc.append("Check: " + "; ".join(r["flags"]))
		description = "\n".join(x for x in desc if x)
		if not dry_run:
			if not frappe.db.exists("Item", code):
				_uom(first["purchase_uom"])
				doc = frappe.get_doc({
					"doctype": "Item", "item_code": code, "item_name": item_name, "item_group": group,
					"stock_uom": first["stock_uom"], "is_stock_item": 1, "is_purchase_item": 1, "is_sales_item": 0,
					"description": description, "purchase_uom": first["purchase_uom"],
				})
				if first["purchase_uom"] != first["stock_uom"]:
					doc.append("uoms", {"uom": first["stock_uom"], "conversion_factor": 1})
					doc.append("uoms", {"uom": first["purchase_uom"], "conversion_factor": first["factor"]})
				sup_seen = {}
				for r in rows:
					sup_seen.setdefault(r["supplier"], []).append(r["supplier_sku"])
				for sname, skus in sup_seen.items():
					sid = frappe.db.get_value("Supplier", {"supplier_name": sname[:140]}, "name")
					if sid:
						doc.append("supplier_items", {"supplier": sid, "supplier_part_no": " / ".join(dict.fromkeys(k for k in skus if k))[:140]})
				if company and rows and frappe.db.get_value("Supplier", {"supplier_name": rows[0]["supplier"][:140]}, "name"):
					doc.append("item_defaults", {"company": company, "default_supplier": frappe.db.get_value(
						"Supplier", {"supplier_name": rows[0]["supplier"][:140]}, "name")})
				doc.insert(ignore_permissions=True)
				created += 1
		else:
			created += 1
		# one buying price per supplier: the latest dated one
		best = {}
		for r in rows:
			if r["last_price"] in (None, 0):
				continue
			if r["supplier"] not in best or r["last_date"] >= best[r["supplier"]]["last_date"]:
				best[r["supplier"]] = r
		for sname, r in best.items():
			sid = frappe.db.get_value("Supplier", {"supplier_name": sname[:140]}, "name")
			if not sid and not dry_run:
				skipped += 1
				continue
			pl = CNY_PRICE_LIST if r["currency"] == "CNY" else PRICE_LIST
			rate = round(r["last_price"] / r["factor"], 6)
			priced += 1
			if dry_run:
				continue
			ex = frappe.db.get_value("Item Price", {"item_code": code, "supplier": sid, "price_list": pl, "buying": 1}, "name")
			if ex:
				frappe.db.set_value("Item Price", ex, {"price_list_rate": rate, "uom": r["stock_uom"], "valid_from": r["last_date"]})
			else:
				frappe.get_doc({"doctype": "Item Price", "item_code": code, "price_list": pl, "supplier": sid,
				                "buying": 1, "uom": r["stock_uom"], "price_list_rate": rate, "currency": r["currency"],
				                "valid_from": r["last_date"], "note": r["price_note"][:140]}).insert(ignore_permissions=True)
	return created, priced, skipped


def run(path, dry_run=True):
	data = json.load(open(path))
	frappe.flags.in_import = True
	if not dry_run:
		_prep()
	print("suppliers (created, existing):", load_suppliers(data, dry_run))
	print("items (created), prices, skipped:", load_items(data, dry_run))
	if dry_run:
		frappe.db.rollback()
		print("DRY RUN, nothing saved")
	else:
		frappe.db.commit()
		print("committed")
