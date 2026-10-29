"""Copy sales products (+ Standard Selling prices) and employees from the old site export
(/tmp/old_master.json, made by export_old.py on erp.fbs-host.com) into hcl-erp.

    run("/tmp/old_master.json", dry_run=True)   # does every insert, then rolls back

Idempotent: existing items / prices / employees (same code / ID) are left as they are.
Item codes and employee IDs are kept. Company "Happy Kitchen" becomes this site's company.
Links that don't exist here (e.g. recipes, not loaded yet) are dropped, not guessed.
"""
import json

import frappe

ERRORS = []
SKIP_ITEM = {"hk_recipe", "hk_recipe_qty"}  # recipes come later, with the item mapping
SKIP_EMP = {"user_id", "leave_approver", "expense_approver", "shift_request_approver", "reports_to",
            "job_applicant", "job_offer", "payroll_cost_center", "employee_advance_account", "default_shift", "grade",
            "holiday_list_name"}


def _guarded(label, fn):
	sp = "imp_" + frappe.generate_hash(length=8)
	frappe.db.savepoint(sp)
	try:
		fn()
		return True
	except Exception as e:
		frappe.db.rollback(save_point=sp)
		frappe.clear_messages()
		ERRORS.append(f"{label}: {type(e).__name__}: {str(e)[:300]}")
		return False


def _fit(doctype, data, skip=()):
	"""Keep only fields this site's doctype has; drop Link values that don't exist here."""
	meta = frappe.get_meta(doctype)
	out = {"doctype": doctype}
	for k, v in data.items():
		if k in skip or v in (None, ""):
			continue
		f = meta.get_field(k)
		if not f or f.fieldtype in ("Section Break", "Column Break", "Tab Break", "HTML", "Button"):
			continue
		if f.fieldtype == "Link" and not frappe.db.exists(f.options, v):
			continue
		if f.fieldtype in ("Table", "Table MultiSelect"):
			rows = []
			for r in v or []:
				row = {kk: vv for kk, vv in _fit(f.options, r).items() if kk != "doctype"}
				if row:
					rows.append(row)
			out[k] = rows
			continue
		out[k] = v
	return out


def _company_swap(rows, old_company, company):
	for r in rows:
		if r.get("company") == old_company:
			r["company"] = company
	return [r for r in rows if not r.get("company") or frappe.db.exists("Company", r["company"])]


def load_items(data, company, counts):
	for it in data["items"]:
		code = it["name"]

		def one(it=it, code=code):
			if frappe.db.exists("Item", code):
				counts["items_existing"] += 1
				return
			for g in (it.get("item_group"),):
				if g and not frappe.db.exists("Item Group", g):
					frappe.get_doc({"doctype": "Item Group", "item_group_name": g, "parent_item_group": "All Item Groups"}).insert(ignore_permissions=True)
			for u in {it.get("stock_uom"), *[r.get("uom") for r in it.get("uoms") or []]} - {None}:
				if not frappe.db.exists("UOM", u):
					frappe.get_doc({"doctype": "UOM", "uom_name": u}).insert(ignore_permissions=True)
			it = dict(it)
			it["item_defaults"] = _company_swap([dict(r) for r in it.get("item_defaults") or []], "Happy Kitchen", company)
			doc = frappe.get_doc({**_fit("Item", it, SKIP_ITEM), "item_code": code})
			doc.insert(ignore_permissions=True)
			counts["items_created"] += 1

		if not _guarded(f"Item {code}", one):
			counts["items_failed"] += 1


def load_prices(data, counts):
	for p in data["prices"]:
		def one(p=p):
			if not frappe.db.exists("Item", p["item_code"]):
				counts["prices_no_item"] += 1
				return
			filters = {"item_code": p["item_code"], "price_list": p["price_list"], "selling": 1}
			if p.get("customer"):
				filters["customer"] = p["customer"]
			if frappe.db.exists("Item Price", filters):
				counts["prices_existing"] += 1
				return
			doc = _fit("Item Price", p)
			doc.update({"selling": 1, "buying": 0})
			frappe.get_doc(doc).insert(ignore_permissions=True)
			counts["prices_created"] += 1

		if not _guarded(f"Price {p['item_code']}", one):
			counts["prices_failed"] += 1


def load_employees(data, company, counts):
	for e in data["employees"]:
		eid = e["name"]

		def one(e=e, eid=eid):
			if frappe.db.exists("Employee", eid):
				counts["employees_existing"] += 1
				return
			if e.get("designation") and not frappe.db.exists("Designation", e["designation"]):
				frappe.get_doc({"doctype": "Designation", "designation_name": e["designation"]}).insert(ignore_permissions=True)
			e = dict(e)
			if e.get("company") == "Happy Kitchen":
				e["company"] = company
			doc = frappe.get_doc(_fit("Employee", e, SKIP_EMP))
			doc.insert(ignore_permissions=True, set_name=eid)
			counts["employees_created"] += 1

		# label by ID only: no personal details in the output
		if not _guarded(f"Employee {eid}", one):
			counts["employees_failed"] += 1


def run(path, dry_run=True):
	data = json.load(open(path))
	ERRORS.clear()
	company = frappe.defaults.get_global_default("company") or frappe.get_all("Company", pluck="name")[0]
	counts = {k: 0 for k in ("items_created", "items_existing", "items_failed", "prices_created", "prices_existing",
	                         "prices_no_item", "prices_failed", "employees_created", "employees_existing", "employees_failed")}
	frappe.flags.in_import = True
	try:
		load_items(data, company, counts)
		load_prices(data, counts)
		load_employees(data, company, counts)
	except Exception:
		frappe.db.rollback()
		raise
	print("company:", company)
	print("counts:", counts)
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
