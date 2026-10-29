"""P10: count sheet, stock take approval flow and the stock update. Rolled back."""

import frappe
from frappe.utils import add_days, flt, nowdate

from happy_kitchen.recipe_management.doctype.stock_take import stock_take as st
from happy_kitchen.recipe_management.doctype.stock_take_sheet import stock_take_sheet as sheet_api

P = "E2E-P10-"


def _check(cond, msg):
	if not cond:
		raise AssertionError(msg)


def _expect_error(fn, msg):
	try:
		fn()
	except frappe.ValidationError:
		return
	raise AssertionError(msg)


def run():
	frappe.set_user("Administrator")
	company = frappe.defaults.get_global_default("company")
	abbr = frappe.db.get_value("Company", company, "abbr")
	dry, fridge = f"Dry Stock - {abbr}", f"Fridge - {abbr}"
	try:
		approver = frappe.get_doc({
			"doctype": "User", "email": "e2e-p10-approver@example.com", "first_name": "E2E Approver",
			"send_welcome_email": 0, "user_type": "System User",
			"roles": [{"role": "Stock Take Approver"}, {"role": "Stock User"}],
		}).insert(ignore_permissions=True)

		flour = frappe.get_doc({
			"doctype": "Item", "item_code": P + "FLOUR", "item_name": P + "FLOUR", "stock_uom": "Gram",
			"item_group": "Ingredients", "is_stock_item": 1,
			"uoms": [{"uom": "Gram", "conversion_factor": 1}, {"uom": "Kg", "conversion_factor": 1000},
			         {"uom": "Box", "conversion_factor": 25000}],
			"item_defaults": [{"company": company, "default_warehouse": dry}],
		}).insert().name
		egg = frappe.get_doc({
			"doctype": "Item", "item_code": P + "EGG", "item_name": P + "EGG", "stock_uom": "Nos",
			"item_group": "Ingredients", "is_stock_item": 1,
			"item_defaults": [{"company": company, "default_warehouse": fridge}],
		}).insert().name
		frappe.get_doc({"doctype": "Item Price", "item_code": egg, "price_list": "Standard Buying",
		                "price_list_rate": 1.5}).insert()
		frappe.get_doc({"doctype": "Item Price", "item_code": flour, "price_list": "Standard Buying",
		                "price_list_rate": 0.02}).insert()

		# sheet: add stocked ingredients, then pack sizes from the items
		sheet = frappe.get_doc({"doctype": "Stock Take Sheet", "sheet_name": P + "SHEET", "company": company,
		                        "items": [{"item": egg}]}).insert()
		_check(sheet.items[0].storage_area == fridge, "storage area from the item's default warehouse")
		_check(sheet_api.add_stocked_ingredients(sheet.name) >= 1, "flour added from stocked ingredients")
		sheet.reload()
		_check({r.item for r in sheet.items} >= {flour, egg}, "both items on the sheet")
		sheet_api.fill_pack_sizes(sheet.name)
		sheet.reload()
		frow = next(r for r in sheet.items if r.item == flour)
		_check(frow.pack_uom == "Box", f"flour pack size Box (Kg is a measure, not a pack), got {frow.pack_uom}")
		# keep only our rows (a real site may have other stocked items)
		sheet.items = [r for r in sheet.items if r.item in (flour, egg)]
		sheet.save()

		name = st.make_stock_take(sheet.name)
		data = st.get_count_sheet(name)
		_check(data["editable"] and len(data["rows"]) == 2, "count sheet ready")
		rows = {r["item"]: r["row"] for r in data["rows"]}
		_expect_error(lambda: st.submit_for_approval(name), "can't submit with uncounted rows unless confirmed")
		_check(len(st.uncounted_items(name)) == 2, "both items are listed as uncounted")

		# blank counts become 0 when the submit is confirmed (a second take, so the main flow below is unchanged)
		name2 = st.make_stock_take(sheet.name, str(add_days(nowdate(), -1)))
		rows2 = {r["item"]: r["row"] for r in st.get_count_sheet(name2)["rows"]}
		st.save_counts(name2, [{"row": rows2[flour], "qty": 300, "packs": [0]}])
		_check([u["item"] for u in st.uncounted_items(name2)] == [egg], "only the egg is uncounted")
		_expect_error(lambda: st.submit_for_approval(name2), "refused without confirming")
		_check(st.submit_for_approval(name2, zero_missing=1) == "Submitted", "submitted with the blank set to 0")
		doc2 = frappe.get_doc("Stock Take", name2)
		eggrow = next(r for r in doc2.items if r.item == egg)
		flrow = next(r for r in doc2.items if r.item == flour)
		_check(eggrow.counted and flt(eggrow.stock_qty) == 0 and eggrow.auto_zero, "the blank egg is counted as 0 and marked")
		_check(flt(flrow.stock_qty) == 300 and not flrow.auto_zero, "the counted flour is left alone")
		_check(doc2.counted_rows == 2, "all rows counted")

		st.save_counts(name, [{"row": rows[flour], "qty": 300, "packs": [2]}, {"row": rows[egg], "qty": 24}])
		doc = frappe.get_doc("Stock Take", name)
		qty = {r.item: flt(r.stock_qty) for r in doc.items}
		_check(qty == {flour: 50300, egg: 24}, f"2 boxes of 25 kg + 300 g loose = 50300 g, 24 eggs; got {qty}")

		doc.reload()
		_expect_error(lambda: doc.submit(), "standard Submit is blocked")
		_check(st.submit_for_approval(name) == "Submitted", "submitted")
		_expect_error(lambda: st.save_counts(name, [{"row": rows[egg], "qty": 1}]), "locked while waiting")
		_expect_error(lambda: st.approve(name), "the submitter can't approve")

		# reject sends it back to Draft, then approve as the other user
		frappe.set_user(approver.name)
		_check(st.reject(name, "recount eggs") == "Draft", "rejected to Draft")
		frappe.set_user("Administrator")
		st.save_counts(name, [{"row": rows[egg], "qty": 30}])
		st.submit_for_approval(name)
		frappe.set_user(approver.name)
		_check(st.approve(name) == "Approved", "approved")
		frappe.set_user("Administrator")

		doc.reload()
		_check(doc.docstatus == 1, "approved count is submitted and locked")
		if st.sync_enabled():
			sr = frappe.get_doc("Stock Reconciliation", doc.stock_reconciliation)
			stock = {(b.item_code, b.warehouse): flt(b.actual_qty)
			         for b in frappe.get_all("Bin", filters={"item_code": ("in", [flour, egg])},
			                                 fields=["item_code", "warehouse", "actual_qty"])}
			_check(stock == {(flour, dry): 50300, (egg, fridge): 30}, f"stock follows the count: {stock}")
			print(f"stock reconciliation {sr.name} ({sr.purpose})")
		_expect_error(lambda: doc.cancel(), "approved stock take can't be cancelled")
		print("ok: stock take e2e passed")
	finally:
		frappe.set_user("Administrator")
		frappe.db.rollback()
		frappe.clear_cache()
