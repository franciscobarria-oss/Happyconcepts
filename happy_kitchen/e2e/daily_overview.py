"""Daily Sales Overview page: grid for a day with a draft order and a submitted one. Rolled back."""

import frappe
from frappe.utils import add_days, nowdate

from happy_kitchen.hk_operations import daily_overview_sheet as sheet

P = "E2E-DSO-"


def _check(cond, msg):
	if not cond:
		raise AssertionError(msg)


def run():
	frappe.set_user("Administrator")
	company = frappe.defaults.get_global_default("company")
	abbr = frappe.db.get_value("Company", company, "abbr")
	day = add_days(nowdate(), 400)  # a day with no real orders
	try:
		group = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
		terr = frappe.db.get_value("Territory", {"is_group": 0}, "name")

		def cust(name, **extra):
			return frappe.get_doc({"doctype": "Customer", "customer_name": P + name, "customer_type": "Company",
			                       "customer_group": group, "territory": terr, **extra}).insert().name

		a = cust("BIG - CWB", hk_sheet_group="E2E IKEA", hk_sheet_label="CWB", hk_sheet_label_zh="銅鑼灣", hk_sheet_sort=1)
		b = cust("BIG - K11", hk_sheet_group="E2E IKEA", hk_sheet_label="K11", hk_sheet_sort=2)
		item = frappe.get_doc({
			"doctype": "Item", "item_code": P + "COOKIE", "item_name": P + "COOKIE", "stock_uom": "Nos",
			"item_group": "Products", "is_stock_item": 1, "is_sales_item": 1, "shelf_life_in_days": 4,
			"hk_item_name_zh": "曲奇",
		}).insert().name

		def order(customer, qty, po, submit):
			so = frappe.get_doc({
				"doctype": "Sales Order", "customer": customer, "company": company, "po_no": po,
				"transaction_date": nowdate(), "delivery_date": day,
				"items": [{"item_code": item, "qty": qty, "rate": 10, "delivery_date": day,
				           "warehouse": f"Finished Goods - {abbr}"}],
			}).insert()
			if submit:
				so.submit()
			return so

		order(a, 20, "PO-A", True)
		order(b, 5, "PO-B", False)  # draft
		data = sheet.build(str(day))
		row = next(r for r in data["rows"] if r["item_code"] == item)
		labels = [c["label"] for c in data["columns"]]
		_check(labels == ["CWB", "K11"], f"columns {labels}")
		_check(row["qtys"] == [20, 5] and row["total"] == 25, f"cells {row['qtys']}")
		_check(row["drafts"] == [False, True], f"draft flags {row['drafts']}")
		_check(str(row["best_before"]) == str(add_days(day, 4)), f"best before {row['best_before']}")
		_check(row["item_name_zh"] == "曲奇", "Chinese name")
		_check(data["columns"][0]["label_zh"] == "銅鑼灣", "location")
		_check(data["footer"][0]["po_refs"] == ["PO-A"], "PO ref")
		need = next(n for n in data["needs"] if n["code"] == item)
		_check(need["need"].startswith("25"), f"need {need}")
		frappe.local.form_dict.date = str(day)
		resp = sheet.sheet(str(day))
		_check(b"Delivery" in resp.data and item.encode() in resp.data, "page renders")
	finally:
		frappe.db.rollback()
	print("daily_overview e2e: ok")
