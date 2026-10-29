"""Idempotent load of Xero sales invoices (as ERPNext Sales Orders) from a prepared JSON.

Run inside the backend container (copy script + json to /tmp first):
    bench --site <site> console   then:
        exec(open("/tmp/import_xero_orders.py").read()); run("/tmp/xero_orders.json", dry_run=True)
dry_run=True creates every order and then rolls back (real validation errors show up).
dry_run=False commits. Orders are created as Drafts (like Email Orders); nothing is submitted.

Matching: customer by exact name; items by item code. An order is identified by title
"<Xero invoice no> | <customer>", so re-running never duplicates. Orders whose PO reference
already exists on an ERP Sales Order (from Email Orders) are skipped. Orders with any line whose
item is not in the ERP are skipped whole and listed, unless allow_partial=True. Credit notes are
listed, not imported.
"""
import json
import frappe

REPORT = {"created": [], "exists": [], "po_dup": [], "no_customer": [], "missing_items": [], "credit_notes": [], "errors": []}


def _customer(name):
	n = frappe.db.get_value("Customer", {"name": name}) or frappe.db.get_value("Customer", {"customer_name": name})
	if n:
		return n
	r = frappe.db.sql("select name from tabCustomer where lower(trim(customer_name))=%s limit 1", (name.strip().lower(),))
	return r[0][0] if r else None


def run(path, dry_run=True, allow_partial=False):
	for k in REPORT:
		REPORT[k] = []
	orders = json.load(open(path))
	po_have = {r[0] for r in frappe.db.sql("select po_no from `tabSales Order` where ifnull(po_no,'')!='' and ifnull(title,'') not like 'INV-%%'")}
	for o in orders:
		inv = o["invoice"]
		if o["type"] == "Sales credit note":
			REPORT["credit_notes"].append((inv, o["customer"], o["total"]))
			continue
		cust = _customer(o["customer"])
		if not cust:
			REPORT["no_customer"].append((inv, o["customer"]))
			continue
		title = f"{inv} | {cust}"[:140]
		if frappe.db.sql("select name from `tabSales Order` where title like %s limit 1", (f"{inv} | %",)):
			REPORT["exists"].append(inv)
			continue
		if o["reference"] and o["reference"].split(" ")[0] in po_have:
			REPORT["po_dup"].append((inv, o["reference"]))
			continue
		lines, miss = [], []
		for l in o["lines"]:
			if not l["qty"]:
				continue  # Xero zero-quantity line
			if l["item"] and frappe.db.exists("Item", l["item"]):
				lines.append({"item_code": l["item"], "qty": l["qty"], "rate": l["rate"],
				              "delivery_date": o["date"], "description": l["desc"]})
			else:
				miss.append((l["item"] or "(blank)", l["desc"], l["qty"]))
		if miss and (not allow_partial or not lines):
			REPORT["missing_items"].append((inv, o["customer"], miss))
			continue
		sp = "xo_" + inv.replace("-", "_")
		frappe.db.savepoint(sp)
		try:
			doc = frappe.get_doc({"doctype": "Sales Order", "customer": cust, "title": title,
			                      "transaction_date": o["date"], "delivery_date": o["date"],
			                      "po_no": o["reference"][:140], "currency": "HKD", "items": lines})
			try:
				doc.insert(ignore_permissions=True)
			except frappe.ValidationError as e:
				if "Customer's Purchase Order" not in str(e):
					raise
				# same customer PO on several Xero invoices: keep the PO in the title, not po_no
				frappe.db.rollback(save_point=sp)
				frappe.db.savepoint(sp)
				doc = frappe.get_doc({"doctype": "Sales Order", "customer": cust, "title": f"{title} | PO {o['reference']}"[:140],
				                      "transaction_date": o["date"], "delivery_date": o["date"],
				                      "currency": "HKD", "items": lines})
				doc.insert(ignore_permissions=True)
			REPORT["created"].append((inv, doc.name, round(doc.grand_total, 2), o["total"], bool(miss)))
		except Exception as e:
			frappe.db.rollback(save_point=sp)
			REPORT["errors"].append((inv, str(e)[:200]))
	if dry_run:
		frappe.db.rollback()
	else:
		frappe.db.commit()
	print("RESULT", json.dumps({k: (v if k in ("errors", "credit_notes", "no_customer", "po_dup", "exists") else len(v)) for k, v in REPORT.items()}, default=str))
	return REPORT
