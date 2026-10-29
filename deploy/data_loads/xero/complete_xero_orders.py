"""Mark imported Xero Sales Orders (title 'INV-%') with delivery_date <= cutoff as Completed.
Submits each Draft, then sets per_delivered/per_billed=100 and status=Completed WITHOUT creating
Delivery Notes, stock movements or Sales Invoices (Xero holds the invoices).
    g=globals(); exec(open("/tmp/complete_xero_orders.py").read(), g); g["run"]("2026-10-23", dry_run=True)
"""
import json
import frappe


def run(cutoff, dry_run=True):
	names = [r[0] for r in frappe.db.sql(
		"select name from `tabSales Order` where title like 'INV-%%' and docstatus=0 and delivery_date<=%s order by name", (cutoff,))]
	ok, errs = 0, []
	for n in names:
		sp = "c_" + n.replace("-", "_")
		frappe.db.savepoint(sp)
		try:
			doc = frappe.get_doc("Sales Order", n)
			doc.flags.ignore_permissions = True
			doc.submit()
			for it in doc.items:
				frappe.db.set_value("Sales Order Item", it.name, {"delivered_qty": it.qty, "billed_amt": it.amount}, update_modified=False)
			frappe.db.set_value("Sales Order", n, {"per_delivered": 100, "per_billed": 100, "billing_status": "Fully Billed",
			                    "delivery_status": "Fully Delivered", "status": "Completed"}, update_modified=False)
			ok += 1
		except Exception as e:
			frappe.db.rollback(save_point=sp)
			errs.append((n, str(e)[:200]))
	got = frappe.db.sql("select status,docstatus,count(*) from `tabSales Order` where title like 'INV-%%' group by 1,2")
	if dry_run:
		frappe.db.rollback()
	else:
		frappe.db.commit()
	print("CRESULT", json.dumps({"ok": ok, "errors": errs[:5], "status_in_txn": got}, default=str))
