"""P15: allergens, label jobs, rendering and the Pi agent calls. Rolled back.

agent_poll commits on purpose (the Pi needs its claim saved at once), so this check
turns frappe.db.commit into a no-op while it runs and rolls everything back after."""

import base64
import json

import frappe
from frappe.utils import nowdate

from happy_kitchen.hk_operations import labels

P = "E2E-P15-"


def _leaf(doctype):
	return frappe.db.get_value(doctype, {"is_group": 0}, "name")


def _item(code, uom, group, warehouse, company, sales=0, **extra):
	frappe.get_doc({
		"doctype": "Item", "item_code": P + code, "item_name": P + code, "stock_uom": uom,
		"item_group": group, "is_stock_item": 1, "is_sales_item": sales, "is_purchase_item": 0 if sales else 1,
		"valuation_rate": 0, "item_defaults": [{"company": company, "default_warehouse": warehouse}], **extra,
	}).insert()
	return P + code


def _recipe(item, rtype, batch_yield, yield_uom, lines):
	return frappe.get_doc({
		"doctype": "Recipe", "item": item, "recipe_name": item, "recipe_type": rtype, "status": "Active",
		"batch_yield": batch_yield, "yield_uom": yield_uom,
		"ingredients": [{"item": i, "qty": q, "uom": u} for i, q, u in lines],
	}).insert().name


def _check(cond, msg):
	if not cond:
		raise AssertionError(msg)


def _order(customer, company, item, qty, warehouse):
	so = frappe.get_doc({
		"doctype": "Sales Order", "customer": customer, "company": company,
		"transaction_date": nowdate(), "delivery_date": nowdate(),
		"items": [{"item_code": item, "qty": qty, "rate": 10, "delivery_date": nowdate(), "warehouse": warehouse}],
	}).insert()
	so.submit()
	return so


def _jobs(so):
	return frappe.get_all("Label Job", filters={"sales_order": so}, fields=["name", "status", "label_count", "hold_reason"])


def run():
	frappe.set_user("Administrator")
	company = frappe.defaults.get_global_default("company")
	abbr = frappe.db.get_value("Company", company, "abbr")
	real_commit = frappe.db.commit
	frappe.db.commit = lambda *a, **k: None
	try:
		for name in ("Gluten", "Eggs", "Milk"):
			_check(frappe.db.exists("Allergen", name), f"allergen {name} seeded by labels_setup")
		_check(frappe.db.exists("Role", labels.AGENT_ROLE), "Label Printer role")

		customer = frappe.get_doc({"doctype": "Customer", "customer_name": P + "Cafe", "customer_type": "Company",
		                           "customer_group": _leaf("Customer Group"), "territory": _leaf("Territory")}).insert().name
		flour = _item("FLOUR", "Gram", "Ingredients", f"Dry Stock - {abbr}", company,
		              hk_label_name="Wheat flour", hk_allergens_checked=1, hk_allergens=[{"allergen": "Gluten"}])
		egg = _item("EGG", "Nos", "Ingredients", f"Fridge - {abbr}", company, weight_per_unit=50, weight_uom="Gram",
		            hk_label_name="Egg", hk_allergens_checked=1, hk_allergens=[{"allergen": "Eggs"}])
		butter = _item("BUTTER", "Gram", "Ingredients", f"Fridge - {abbr}", company, hk_label_name="Butter")
		dough = _item("DOUGH", "Gram", "Doughs", f"Freezer - {abbr}", company)
		cookie = _item("COOKIE", "Nos", "Products", f"Finished Goods - {abbr}", company, sales=1,
		               shelf_life_in_days=5, hk_storage="Ambient", hk_net_weight_g=80, hk_units_per_label=12)
		# dough (sub-recipe) = 600 g flour + 2 eggs (100 g) + 300 g butter per 1000 g
		_recipe(dough, "Batch Preparation", 1000, "Gram", [(flour, 600, "g"), (egg, 2, "piece"), (butter, 300, "g")])
		_recipe(cookie, "Finished Product", 10, "Nos", [(dough, 800, "g")])

		# --- content: sub-recipe broken down, heaviest first, allergen union ---
		content = labels.label_content(cookie)
		_check(content["ingredients"].startswith("Wheat flour") and "Butter" in content["ingredients"]
		       and "Egg" in content["ingredients"], f"ingredient list {content['ingredients']!r}")
		_check(set(content["allergens"]) == {"Gluten", "Eggs"}, f"allergens {content['allergens']}")
		_check(content["unchecked_allergens"] == [butter], f"butter not reviewed: {content['unchecked_allergens']}")
		_check(labels.label_state(cookie, content)["state"] == "Not checked", "new label is not checked")

		printer = frappe.get_doc({"doctype": "Label Printer", "printer_name": P + "Zebra", "enabled": 1,
		                          "mode": "ZPL", "dpi": "203", "width_mm": 100, "height_mm": 150}).insert().name
		frappe.db.set_single_value("Label Settings", {"default_printer": printer, "create_on_submit": 1})

		# --- order before the check: the job waits ---
		so1 = _order(customer, company, cookie, 30, f"Finished Goods - {abbr}")
		jobs = _jobs(so1.name)
		_check(len(jobs) == 1 and jobs[0].status == "Needs check", f"job waits for the check: {jobs}")
		_check(jobs[0].label_count == 3, f"30 pieces at 12 per label = 3 labels: {jobs}")

		# --- butter still unreviewed: can't check; review it, then check releases the job ---
		try:
			labels.mark_label_checked(cookie)
			_check(False, "check must refuse while butter allergens are unreviewed")
		except frappe.ValidationError:
			pass
		b = frappe.get_doc("Item", butter)
		b.append("hk_allergens", {"allergen": "Milk"})
		b.hk_allergens_checked = 1
		b.save()
		released = labels.mark_label_checked(cookie)["released"]
		_check(released == 1, f"check releases the waiting job: {released}")
		job = jobs[0].name
		_check(frappe.db.get_value("Label Job", job, "status") == "Queued", "job queued after the check")
		data = json.loads(frappe.db.get_value("Label Job", job, "label_json"))
		_check(set(data["allergens"]) == {"Gluten", "Eggs", "Milk"}, f"released job has milk: {data['allergens']}")

		# --- previews: PNG ---
		png = base64.b64decode(labels.job_preview(job)["png"])
		_check(png[:8] == b"\x89PNG\r\n\x1a\n", "job preview is a PNG")
		_check(base64.b64decode(labels.item_label_preview(cookie)["png"])[:4] == b"\x89PNG", "item preview is a PNG")

		# --- Pi agent: poll hands over ZPL, done marks it printed ---
		got = labels.agent_poll(printer, agent_version="e2e", host="e2e-pi")
		_check(got["job"] == job and got["format"] == "zpl", f"poll hands over the job: {got.get('job')}")
		_check(got["count"] == 3 and all(l["zpl"].startswith("^XA") for l in got["labels"]), "ZPL for 3 labels")
		_check(sum(l["copies"] for l in got["labels"]) == 3, "12 + 12 + 6 pieces as copies")
		_check(frappe.db.get_value("Label Job", job, "status") == "Printing", "claimed")
		_check(labels.agent_done(printer, job, ok=1) == "Printed", "printed")
		_check(labels.agent_poll(printer)["job"] is None, "nothing left to print")
		_check(labels.printer_status(printer)["online"], "printer seen just now")

		# --- Today home shows the order's label status ---
		from happy_kitchen.recipe_management import today

		going = {o["name"]: o for o in today.today()["now"]["orders"]}
		_check((going.get(so1.name) or {}).get("labels", {}).get("printed") == 3, f"Today shows 3 labels printed: {going.get(so1.name)}")

		# --- checked product: new order queues straight away; cancelling the order cancels it ---
		so2 = _order(customer, company, cookie, 12, f"Finished Goods - {abbr}")
		jobs = _jobs(so2.name)
		_check(len(jobs) == 1 and jobs[0].status == "Queued", f"checked label prints at once: {jobs}")
		so2.reload()
		so2.cancel()
		_check(frappe.db.get_value("Label Job", jobs[0].name, "status") == "Cancelled", "cancelled with the order")

		# --- Ingredient Label Check report lists the three bought-in ingredients ---
		from happy_kitchen.hk_operations.report.ingredient_label_check import ingredient_label_check as ilc

		_, rows = ilc.execute({"only_open": 0})
		mine = {r["item"]: r for r in rows if r["item"].startswith(P)}
		_check(set(mine) == {flour, egg, butter}, f"report rows {sorted(mine)}")
		_check(mine[butter]["allergens"] == "Milk" and mine[butter]["to_do"] == "", f"butter row {mine[butter]}")
		print("ok: labels e2e passed")
	finally:
		frappe.db.commit = real_commit
		frappe.db.rollback()
		frappe.clear_cache()
