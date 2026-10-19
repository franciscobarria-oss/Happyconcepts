"""P15b: lots and batches on production, the Opened item, kitchen date labels and the
Use-by list on Today. Rolled back. agent_poll commits on purpose, so commit is a no-op here."""

import json

import frappe
from frappe.utils import add_days, flt, nowdate

from happy_kitchen.hk_operations import dates_api, labels
from happy_kitchen.recipe_management import kitchen

P = "E2E-P15B-"


def _check(cond, msg):
	if not cond:
		raise AssertionError(msg)


def _item(code, uom, group, warehouse, company, **extra):
	frappe.get_doc({
		"doctype": "Item", "item_code": P + code, "item_name": P + code, "stock_uom": uom,
		"item_group": group, "is_stock_item": 1, "valuation_rate": 0,
		"item_defaults": [{"company": company, "default_warehouse": warehouse}], **extra,
	}).insert()
	return P + code


def _recipe(item, rtype, batch_yield, yield_uom, lines):
	return frappe.get_doc({
		"doctype": "Recipe", "item": item, "recipe_name": item, "recipe_type": rtype, "status": "Active",
		"batch_yield": batch_yield, "yield_uom": yield_uom,
		"ingredients": [{"item": i, "qty": q, "uom": u} for i, q, u in lines],
	}).insert().name


def run():
	frappe.set_user("Administrator")
	company = frappe.defaults.get_global_default("company")
	abbr = frappe.db.get_value("Company", company, "abbr")
	real_commit = frappe.db.commit
	frappe.db.commit = lambda *a, **k: None
	try:
		frappe.db.set_single_value("Recipe Settings", "create_stock_entry_on_submit", 1)
		frappe.clear_document_cache("Recipe Settings", "Recipe Settings")
		_check(frappe.db.exists("Warehouse", f"Chiller - {abbr}"), "Chiller warehouse exists")
		for f in ("hk_open_life_value", "hk_open_life_unit", "hk_open_storage"):
			_check(frappe.get_meta("Item").has_field(f), f"Item field {f}")

		flour = _item("FLOUR", "Gram", "Ingredients", f"Dry Stock - {abbr}", company)
		milk = _item("MILK", "Nos", "Ingredients", f"Fridge - {abbr}", company,
		             hk_open_life_value=6, hk_open_life_unit="Hours", hk_open_storage="Chilled", hk_item_name_zh="鮮奶")
		# the dough already tracks batches (set here, never by the app); the cookie does not
		dough = _item("DOUGH", "Gram", "Doughs", f"Chiller - {abbr}", company, has_batch_no=1, create_new_batch=0,
		              shelf_life_in_days=3, hk_open_storage="Chilled")
		cookie = _item("COOKIE", "Nos", "Products", f"Finished Goods - {abbr}", company, shelf_life_in_days=2)
		frappe.get_doc({
			"doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "purpose": "Material Receipt", "company": company,
			"items": [{"item_code": flour, "qty": 5000, "basic_rate": 0.02, "t_warehouse": f"Dry Stock - {abbr}"}],
		}).insert().submit()
		dough_r = _recipe(dough, "Batch Preparation", 1000, "Gram", [(flour, 600, "g")])
		cookie_r = _recipe(cookie, "Finished Product", 10, "Nos", [(flour, 200, "g")])

		printer = frappe.get_doc({"doctype": "Label Printer", "printer_name": P + "SATO", "enabled": 1, "mode": "ZPL",
		                          "label_use": "Kitchen date labels"}).insert()
		_check((flt(printer.width_mm), flt(printer.height_mm)) == (50, 30), "kitchen printer defaults to 50 x 30 mm")
		frappe.db.set_single_value("Label Settings", {"date_label_printer": printer.name, "batch_labels_on_submit": 1})
		frappe.clear_document_cache("Label Settings", "Label Settings")

		# --- production: lots, an ERPNext Batch for the batch-tracked dough only, batch labels ---
		res = kitchen.log_production([{"recipe": dough_r, "batches": 1}, {"recipe": cookie_r, "batches": 1}])
		log = frappe.get_doc("Recipe Production Log", res["name"])
		d_row, c_row = log.items
		lot = "L" + nowdate().replace("-", "")[2:]
		_check(d_row.lot_no == lot and c_row.lot_no == lot + "-2", f"lots {d_row.lot_no}, {c_row.lot_no}")
		_check(str(d_row.use_by) == add_days(nowdate(), 3) and str(c_row.use_by) == add_days(nowdate(), 2), "use by = made on + shelf life")
		_check(d_row.batch_no and frappe.db.get_value("Batch", d_row.batch_no, "item") == dough, "ERPNext Batch for the batch-tracked item")
		_check(not c_row.batch_no, "no Batch for an item that does not track batches")
		mfg = frappe.get_doc("Stock Entry", log.batch_stock_entries.split()[0])
		out = next(d for d in mfg.items if d.item_code == dough)
		_check(out.batch_no == d_row.batch_no, "Manufacture output row carries the batch")
		jobs = frappe.get_all("Label Job", filters={"production_log": log.name}, fields=["name", "kind", "status", "printer"])
		_check(len(jobs) == 2 and all(j.kind == "Batch" and j.status == "Queued" and j.printer == printer.name for j in jobs), f"batch jobs {jobs}")

		more = dates_api.print_batch_labels(log.name, labels=3)
		_check(len(more) == 2, "Print batch labels queues one job per row")
		_check(frappe.db.get_value("Label Job", more[0], "label_count") == 3, "3 labels asked for")

		# --- the Pi agent renders the small label; preview works ---
		poll = labels.agent_poll(printer.name)
		_check(poll["job"] and poll["format"] == "zpl" and poll["labels"][0]["zpl"].startswith("^XA"), "agent gets ZPL for the kitchen label")
		_check(labels.job_preview(more[0])["png"], "kitchen label preview")

		# --- Opened screen ---
		found = dates_api.find_item(milk)
		_check(found and found["open_life_set"] and found["lots"] == [], f"find_item {found}")
		r = dates_api.open_item(milk, labels=2)
		op = frappe.get_doc("Opened Item", r["name"])
		_check(op.use_by and op.status == "Open" and op.storage == "Chilled", "opened item has a use-by")
		job = frappe.get_doc("Label Job", r["label_job"])
		lines = json.loads(job.label_json)["lines"]
		_check(job.kind == "Opened" and job.label_count == 2 and ["title", milk] in lines, f"opened job {lines}")
		_check(any(t.startswith("USE BY") for _s, t in lines), "USE BY line")
		try:
			dates_api.open_item(flour)
			raise AssertionError("an item with no open life must be refused")
		except frappe.ValidationError:
			pass

		# --- Today: past-use-by list and Discarded -> Wastage Log ---
		frappe.db.set_value("Opened Item", op.name, "use_by", f"{add_days(nowdate(), -1)} 10:00:00")
		frappe.db.set_value("Recipe Production Log Item", c_row.name, "use_by", add_days(nowdate(), -1))
		listed = {(x["kind"], x["name"]): x for x in dates_api.expiring()}
		_check(listed[("Opened Item", op.name)]["state"] == "past", "opened item is past use-by")
		_check(("Recipe Production Log", log.name) in listed, "batch row listed")
		closed = dates_api.close("Opened Item", op.name, action="Discarded", qty=2, uom="piece")
		wl = frappe.get_doc("Wastage Log", closed["wastage_log"])
		_check(wl.items[0].item == milk and flt(wl.items[0].qty) == 2, "Wastage Log line for the discarded item")
		_check(frappe.db.get_value("Opened Item", op.name, "status") == "Discarded", "opened item closed")
		dates_api.close("Recipe Production Log", log.name, row=c_row.name, action="Used up")
		left = [x for x in dates_api.expiring() if x["name"] == op.name or x["row"] == c_row.name]
		_check(not left, "closed lines leave the list")
		_check("dates" in __import__("happy_kitchen.recipe_management.today", fromlist=["today"]).today(), "Today carries the dates list")
		print("ok: dates e2e passed", nowdate())
	finally:
		frappe.db.commit = real_commit
		frappe.db.rollback()
		frappe.clear_document_cache("Recipe Settings", "Recipe Settings")
		frappe.clear_document_cache("Label Settings", "Label Settings")
		frappe.clear_cache()
