"""One-off, idempotent load of suppliers + purchase items from a purchase_master.json
(built from the Ingredients_<month>_2026 workbooks).

Run inside the backend container (copy both files to /tmp first):
    bench --site <site> console   then:
        exec(open("/tmp/import_purchases.py").read()); run("/tmp/purchase_master.json", dry_run=True)
    dry_run=True performs every insert (so real validation errors show up) and then rolls back.
    dry_run=False commits.

Re-running is safe: suppliers and items are matched by name/code, prices are updated in place.
Each record runs inside a savepoint; a failing record is reported and skipped, the rest continue.
"""
import json
import re

import frappe

PRICE_LIST = "Standard Buying"
CNY_PRICE_LIST = "Taobao Buying (CNY)"
GROUPS = {"Trade Supplier": "Trade Supplier", "Retail": "Retail", "Online (Taobao)": "Online (Taobao)"}
ITEM_GROUPS = ("Ingredients", "Packaging")
ERRORS = []


def _ensure(doctype, name, **vals):
	if frappe.db.exists(doctype, name):
		return name
	doc = frappe.get_doc({"doctype": doctype, **vals})
	doc.insert(ignore_permissions=True)
	return doc.name


def _root(doctype, parent_field, fallback):
	rows = frappe.db.sql(
		f"select name from `tab{doctype}` where coalesce({parent_field}, '') = '' order by lft limit 1")
	return rows[0][0] if rows else fallback


def _prep():
	root = _root("Supplier Group", "parent_supplier_group", "All Supplier Groups")
	for g in GROUPS.values():
		_ensure("Supplier Group", g, supplier_group_name=g, parent_supplier_group=root)
	iroot = _root("Item Group", "parent_item_group", "All Item Groups")
	for g in ITEM_GROUPS:
		_ensure("Item Group", g, item_group_name=g, parent_item_group=iroot, is_group=0)
	if frappe.db.exists("Currency", "CNY"):
		frappe.db.set_value("Currency", "CNY", "enabled", 1)
	_ensure("Price List", CNY_PRICE_LIST, price_list_name=CNY_PRICE_LIST, currency="CNY", buying=1, selling=0, enabled=1)


def _uom(name):
	if not frappe.db.exists("UOM", name):
		frappe.get_doc({"doctype": "UOM", "uom_name": name, "must_be_whole_number": 1}).insert(ignore_permissions=True)


def _clean_email(s):
	for part in re.split(r"[;,/ ]+", s or ""):
		if re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", part):
			return part
	return ""


def _clean_phone(s):
	"""First phone number in a free-text field like "(852) 2553 8573; Fax ..." -> "+852 2553 8573"."""
	s = re.sub(r"\(\s*\+?852\s*\)", "+852 ", (s or "").lstrip("'"))
	m = re.search(r"\+?\d[\d \-]{6,}\d", s)
	return re.sub(r"\s+", " ", m.group(0)).strip() if m else ""


def _guarded(label, fn):
	"""Run fn inside a savepoint; on error roll back just that record and log it."""
	sp = "imp_" + frappe.generate_hash(length=8)
	frappe.db.savepoint(sp)
	try:
		fn()
		return True
	except Exception as e:
		frappe.db.rollback(save_point=sp)
		frappe.clear_messages()
		ERRORS.append(f"{label}: {type(e).__name__}: {e}")
		return False


def _supplier_id(sname):
	return frappe.db.get_value("Supplier", {"supplier_name": sname[:140]}, "name")


def _load_supplier(s, counts):
	name = s["name"][:140]
	details = []
	for label, key in (("Payment terms", "payment_terms"), ("Delivery minimum", "moq"), ("Contact", "contact"),
	                   ("Phone", "phone"), ("Email", "email"), ("Address", "address")):
		if s.get(key):
			details.append(f"{label}: {s[key]}")
	details.append(f"Seen on invoices {s['first']} to {s['last']} ({s['invoices']} invoices), loaded from purchase workbooks Jun-Sep 2026.")
	vals = {"supplier_group": GROUPS[s["group"]], "supplier_type": "Company", "default_currency": s["currency"],
	        "supplier_details": "\n".join(details), "website": (s.get("website") or "")[:140]}
	existing = _supplier_id(name)
	if existing:
		doc = frappe.get_doc("Supplier", existing)
		changed = False
		for k, v in vals.items():
			if v and not doc.get(k):
				doc.set(k, v)
				changed = True
		if changed:
			doc.save(ignore_permissions=True)
		outcome = "existing"
	else:
		existing = frappe.get_doc({"doctype": "Supplier", "supplier_name": name, **vals}).insert(ignore_permissions=True).name
		outcome = "created"
	phone = _clean_phone(s.get("phone"))
	link = {"link_doctype": "Supplier", "link_name": existing}
	if s.get("address") and not frappe.db.exists("Dynamic Link", {"link_doctype": "Supplier", "link_name": existing, "parenttype": "Address"}):
		hk = s["currency"] == "HKD"
		frappe.get_doc({"doctype": "Address", "address_title": name[:100], "address_type": "Billing",
		                "address_line1": s["address"][:140], "city": "Hong Kong" if hk else "-",
		                "country": "Hong Kong" if hk else "China",
		                "phone": phone, "email_id": _clean_email(s.get("email")),
		                "links": [link]}).insert(ignore_permissions=True)
	if (s.get("contact") or s.get("phone") or s.get("email")) and not frappe.db.exists(
			"Dynamic Link", {"link_doctype": "Supplier", "link_name": existing, "parenttype": "Contact"}):
		c = {"doctype": "Contact", "first_name": (s.get("contact") or name)[:140], "links": [link]}
		if _clean_email(s.get("email")):
			c["email_ids"] = [{"email_id": _clean_email(s["email"]), "is_primary": 1}]
		if phone:
			c["phone_nos"] = [{"phone": phone, "is_primary_phone": 1}]
		frappe.get_doc(c).insert(ignore_permissions=True)
	counts[outcome] += 1


def load_suppliers(data):
	counts = {"created": 0, "existing": 0, "failed": 0}
	for s in data["suppliers"]:
		if not _guarded(f"Supplier {s['name']}", lambda s=s: _load_supplier(s, counts)):
			counts["failed"] += 1
	return counts


def _load_item(code, rows, item_name, company, counts):
	first = rows[0]
	if frappe.db.exists("Item", code):
		outcome = "existing"
	else:
		outcome = "created"
		group = "Packaging" if first["category"] == "packaging" else "Ingredients"
		desc = [first["presentation"] and f"Pack: {first['presentation']}", f"Bought per {first['purchase_uom']} = {first['size_basis']}"]
		for r in rows:
			desc.append(f"[{r['supplier']}] {r['price_note']}" if r["price_note"] else "")
			if r["flags"]:
				desc.append("Check: " + "; ".join(r["flags"]))
		_uom(first["stock_uom"])
		_uom(first["purchase_uom"])
		doc = frappe.get_doc({
			"doctype": "Item", "item_code": code, "item_name": item_name, "item_group": group,
			"stock_uom": first["stock_uom"], "is_stock_item": 1, "is_purchase_item": 1, "is_sales_item": 0,
			"description": "\n".join(x for x in desc if x), "purchase_uom": first["purchase_uom"],
		})
		if first["purchase_uom"] != first["stock_uom"]:
			doc.append("uoms", {"uom": first["stock_uom"], "conversion_factor": 1})
			doc.append("uoms", {"uom": first["purchase_uom"], "conversion_factor": first["factor"]})
		sup_seen = {}
		for r in rows:
			sup_seen.setdefault(r["supplier"], []).append(r["supplier_sku"])
		for sname, skus in sup_seen.items():
			sid = _supplier_id(sname)
			if sid:
				doc.append("supplier_items", {"supplier": sid, "supplier_part_no": " / ".join(dict.fromkeys(k for k in skus if k))[:140]})
		default_sup = _supplier_id(first["supplier"])
		if company and default_sup:
			doc.append("item_defaults", {"company": company, "default_supplier": default_sup})
		doc.insert(ignore_permissions=True)
	# one buying price per supplier: the latest dated one
	best = {}
	for r in rows:
		if r["last_price"] in (None, 0):
			continue
		if r["supplier"] not in best or r["last_date"] >= best[r["supplier"]]["last_date"]:
			best[r["supplier"]] = r
	price_counts = {"prices_created": 0, "prices_updated": 0, "price_skipped": 0}
	for sname, r in best.items():
		sid = _supplier_id(sname)
		if not sid:
			price_counts["price_skipped"] += 1
			continue
		pl = CNY_PRICE_LIST if r["currency"] == "CNY" else PRICE_LIST
		rate = round(r["last_price"] / r["factor"], 6)
		ex = frappe.db.get_value("Item Price", {"item_code": code, "supplier": sid, "price_list": pl, "buying": 1}, "name")
		if ex:
			frappe.db.set_value("Item Price", ex, {"price_list_rate": rate, "uom": r["stock_uom"], "valid_from": r["last_date"]})
			price_counts["prices_updated"] += 1
		else:
			frappe.get_doc({"doctype": "Item Price", "item_code": code, "price_list": pl, "supplier": sid,
			                "buying": 1, "uom": r["stock_uom"], "price_list_rate": rate, "currency": r["currency"],
			                "valid_from": r["last_date"], "note": (r["price_note"] or "")[:140]}).insert(ignore_permissions=True)
			price_counts["prices_created"] += 1
	counts[outcome] += 1
	for k, v in price_counts.items():
		counts[k] += v


def load_items(data):
	company = frappe.defaults.get_global_default("company")
	by_code = {}
	for it in data["items"]:
		by_code.setdefault(it["item_code"], []).append(it)
	names_used = {}
	counts = {"created": 0, "existing": 0, "failed": 0, "prices_created": 0, "prices_updated": 0, "price_skipped": 0}
	for code, rows in by_code.items():
		first = rows[0]
		base = first["item_name"].strip()[:130]
		suffix = f" ({first['purchase_uom']})" if names_used.get(base.lower(), code) != code else ""
		names_used[base.lower()] = code
		if not _guarded(f"Item {code}", lambda: _load_item(code, rows, base + suffix, company, counts)):
			counts["failed"] += 1
	return counts


def run(path, dry_run=True):
	data = json.load(open(path))
	ERRORS.clear()
	frappe.flags.in_import = True
	try:
		_prep()
		print("suppliers:", load_suppliers(data))
		print("items:", load_items(data))
	except Exception:
		frappe.db.rollback()
		raise
	print(f"errors: {len(ERRORS)}")
	for e in ERRORS:
		print("  ", e)
	if dry_run:
		frappe.db.rollback()
		print("DRY RUN, rolled back, nothing saved")
	else:
		frappe.db.commit()
		print("committed")
	return ERRORS
