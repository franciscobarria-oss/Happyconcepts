"""Sales block on the Selling workspace: units per SKU, per week and by weekday, drafts only on
request, the block placed on the workspace. Rolled back."""

import json

import frappe
from frappe.utils import add_days, getdate, nowdate

from happy_kitchen.hk_operations import sales_api

P = "E2E-SALES-"


def _leaf(doctype):
	return frappe.db.get_value(doctype, {"is_group": 0}, "name")


def _check(cond, msg):
	if not cond:
		raise AssertionError(msg)


def run():
	frappe.set_user("Administrator")
	company = frappe.defaults.get_global_default("company")
	abbr = frappe.db.get_value("Company", company, "abbr")
	wh = f"Finished Goods - {abbr}"
	# a fixed Tuesday far in the future, so real orders never mix in
	tue = getdate("2099-06-02")
	try:
		customer = frappe.get_doc({"doctype": "Customer", "customer_name": P + "Cafe", "customer_type": "Company",
		                           "customer_group": _leaf("Customer Group"), "territory": _leaf("Territory")}).insert().name
		item = frappe.get_doc({"doctype": "Item", "item_code": P + "BUN", "item_name": P + "BUN", "stock_uom": "Nos",
		                       "item_group": "Products", "is_stock_item": 1, "is_sales_item": 1}).insert().name

		def order(day, qty, submit=True):
			so = frappe.get_doc({
				"doctype": "Sales Order", "customer": customer, "company": company,
				"transaction_date": nowdate(), "delivery_date": day,
				"items": [{"item_code": item, "qty": qty, "rate": 5, "delivery_date": day, "warehouse": wh}],
			}).insert()
			if submit:
				so.submit()
			return so

		order(tue, 10)
		order(add_days(tue, 7), 4)
		order(add_days(tue, 8), 6)
		order(add_days(tue, 1), 100, submit=False)

		lo, hi = str(add_days(tue, -1)), str(add_days(tue, 12))
		d = sales_api.sales(lo, hi, item_code=item)
		_check(d["totals"]["qty"] == 20, f"confirmed units: {d['totals']}")
		_check(d["draft_orders"] == 1, f"drafts counted: {d['draft_orders']}")
		_check([w["qty"] for w in d["weeks"]] == [10, 10], f"weeks: {d['weeks']}")
		_check(d["recent"]["busiest_weekday"] == "Tue", f"busiest: {d['recent']}")
		_check(d["skus"][0]["orders"] == 3, f"orders per SKU: {d['skus']}")

		d = sales_api.sales(lo, hi, include_drafts=1, item_code=item)
		_check(d["totals"]["qty"] == 120, f"with drafts: {d['totals']}")
		_check(d["recent"]["busiest_weekday"] == "Wed", f"busiest with drafts: {d['recent']}")

		content = json.loads(frappe.db.get_value("Workspace", "Selling", "content") or "[]")
		_check(content and content[0].get("data", {}).get("custom_block_name") == "HK Sales",
		       "HK Sales is not on top of the Selling workspace")
		print("sales e2e: ok")
	finally:
		frappe.db.rollback()
