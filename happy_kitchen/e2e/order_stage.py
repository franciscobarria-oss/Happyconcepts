"""Sales Order stage: Draft -> Confirmed -> Complete -> Completed, with and without a Delivery
Note (Recipe Settings complete_with_delivery_note). Rolled back."""

import frappe
from frappe.utils import add_days, nowdate

from happy_kitchen.hk_operations import order_stage, order_stage_api

P = "E2E-STAGE-"


def _leaf(doctype):
	return frappe.db.get_value(doctype, {"is_group": 0}, "name")


def _check(cond, msg):
	if not cond:
		raise AssertionError(msg)


def _stage(so):
	return order_stage.stage(so.docstatus, so.status, so.per_delivered, so.per_billed, so.delivery_date, nowdate())


def run():
	frappe.set_user("Administrator")
	company = frappe.defaults.get_global_default("company")
	abbr = frappe.db.get_value("Company", company, "abbr")
	day = add_days(nowdate(), 1)
	try:
		customer = frappe.get_doc({"doctype": "Customer", "customer_name": P + "Cafe", "customer_type": "Company",
		                           "customer_group": _leaf("Customer Group"), "territory": _leaf("Territory")}).insert().name
		item = frappe.get_doc({"doctype": "Item", "item_code": P + "CAKE", "item_name": P + "CAKE", "stock_uom": "Nos",
		                       "item_group": "Products", "is_stock_item": 0, "is_sales_item": 1}).insert().name
		def order():
			so = frappe.get_doc({
				"doctype": "Sales Order", "customer": customer, "company": company,
				"transaction_date": nowdate(), "delivery_date": day,
				"items": [{"item_code": item, "qty": 3, "rate": 10, "delivery_date": day,
				           "warehouse": f"Finished Goods - {abbr}"}],
			}).insert()
			_check(_stage(so)["stage"] == "Draft", f"new order: {_stage(so)}")
			so.submit()
			_check(_stage(so)["stage"] == "Confirmed", f"submitted: {_stage(so)}")
			return so

		def refused(name, what):
			try:
				order_stage_api.mark_delivered(name)
			except frappe.ValidationError:
				return
			raise AssertionError(what)

		# stock not tracked (Recipe Settings default): Complete closes the order, no Delivery Note
		frappe.db.set_single_value("Recipe Settings", "complete_with_delivery_note", 0)
		so = order()
		frappe.db.set_value("Sales Order", so.name, "hk_needs_review", 1)
		refused(so.name, "a revised order was completed")
		frappe.db.set_value("Sales Order", so.name, "hk_needs_review", 0)
		dns = frappe.db.count("Delivery Note")
		r = order_stage_api.mark_delivered(so.name)
		so.reload()
		s = _stage(so)
		_check(r["delivery_note"] is None and so.status == "Closed", f"closed: {r} {so.status}")
		_check(s["stage"] == "Completed" and s["no_delivery_note"], f"after complete: {s}")
		_check(frappe.db.count("Delivery Note") == dns, "a delivery note was made")
		refused(so.name, "completed twice")

		# stock tracked: Complete makes and submits one Delivery Note
		frappe.db.set_single_value("Recipe Settings", "complete_with_delivery_note", 1)
		so = order()
		dn = order_stage_api.mark_delivered(so.name)["delivery_note"]
		_check(frappe.db.get_value("Delivery Note", dn, "docstatus") == 1, "delivery note not submitted")
		so.reload()
		s = _stage(so)
		_check(s["stage"] == "Completed" and not s["invoiced"] and not s["no_delivery_note"],
		       f"after delivery: {s} ({so.per_delivered}%)")
		refused(so.name, "delivered twice")
		print("order stage e2e: ok")
	finally:
		frappe.db.rollback()
