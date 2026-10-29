"""Product labels for confirmed sales orders.

Labels are optional and never prompted: staff print them from the order's
Labels menu ("Print labels"). Only when Label Settings "Create labels when a
sales order is submitted" is ticked (off by default) does submitting add one
Label Job per line, silently. A job prints straight
away when its product's label has been checked by a person ("Label checked" on
the Item's Label tab) and nothing on it has changed since; otherwise it waits
as "Needs check". A small program on a Raspberry Pi (label_agent/ in this app)
asks agent_poll for work every few seconds, prints on the USB label printer
and reports back with agent_done.
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, flt, getdate, now_datetime, nowdate

from happy_kitchen.hk_operations import label_data as ld
from happy_kitchen.hk_operations import label_render as lr
from happy_kitchen.recipe_management.pricing import SUB_RECIPE_TYPES

SETTINGS = "Label Settings"
AGENT_ROLE = "Label Printer"
CHECK_ROLES = ("System Manager", "Sales Manager", "Stock Manager", "Item Manager", "Manufacturing Manager")
DONE = ("Printed", "Cancelled")
STUCK_MINUTES = 10
ONLINE_SECONDS = 120


# ------------------------------------------------------------- label content --

def _recipe_tables():
	"""Recipe lines and which recipe makes which item (active recipes first)."""
	recipes = frappe.get_all("Recipe", fields=["name", "item", "recipe_type", "batch_yield", "status", "unit_weight"])
	rank = {"Active": 0, "Draft": 1, "Archived": 2}
	own, subs = {}, {}
	for r in sorted(recipes, key=lambda r: rank.get(r.status, 3)):
		info = {"recipe": r.name, "batch_yield": flt(r.batch_yield) or 1.0, "unit_weight": flt(r.unit_weight)}
		own.setdefault(r.item, info)
		if r.recipe_type in SUB_RECIPE_TYPES and r.status != "Archived":
			subs.setdefault(r.item, info)
	lines: dict[str, list] = {}
	for l in frappe.get_all(
		"Recipe Ingredient", filters={"parenttype": "Recipe"},
		fields=["parent", "item", "gross_qty", "stock_uom", "component_type", "grams_per_piece"], order_by="parent, idx",
	):
		lines.setdefault(l.parent, []).append(l)
	return own, subs, lines


def _oem_spec(customer: str | None, item: str) -> dict:
	if not customer or not frappe.db.exists("DocType", "OEM Spec Sheet"):
		return {}
	rows = frappe.get_all(
		"OEM Spec Sheet", filters={"customer": customer, "item": item, "status": "Approved"},
		fields=["name", "shelf_life_days", "storage"], order_by="version desc", limit=1,
	)
	return rows[0] if rows else {}


def label_content(item_code: str, customer: str | None = None) -> dict:
	"""Everything printed on a product's label except the dates."""
	item = frappe.get_doc("Item", item_code)
	own, subs, lines = _recipe_tables()
	top, factor = item_code, 1.0
	if item.get("hk_recipe"):
		target = frappe.db.get_value("Recipe", item.hk_recipe, "item")
		if target:
			top, factor = target, flt(item.get("hk_recipe_qty")) or 1.0

	weights, warnings = {}, []
	if top in own:
		recipe_for_item = dict(subs)
		recipe_for_item[top] = own[top]
		pieces = _piece_grams(lines)
		weights, warnings = ld.ingredient_weights(top, recipe_for_item, lines, pieces, factor)

	codes = list(weights)
	meta = {
		i.name: i
		for i in frappe.get_all(
			"Item", filters={"name": ("in", codes or [""])},
			fields=["name", "item_name", "hk_label_name", "hk_allergens_checked"],
		)
	}
	names = {c: (meta[c].hk_label_name or meta[c].item_name) if c in meta else c for c in codes}
	rows = ld.ingredient_list(weights, names)
	item_allergens: dict[str, list[str]] = {}
	for a in frappe.get_all("Item Allergen", filters={"parenttype": "Item", "parent": ("in", codes or [""])},
	                        fields=["parent", "allergen"]):
		item_allergens.setdefault(a.parent, []).append(a.allergen)
	allergen_rows = frappe.get_all("Allergen", filters={"disabled": 0}, fields=["name", "label_phrase"],
	                               order_by="sort_order asc, name asc")
	order = [a.name for a in allergen_rows]
	phrase = {a.name: (a.label_phrase or a.name.lower()) for a in allergen_rows}

	spec = _oem_spec(customer, item_code)
	storage_key = spec.get("storage") or item.get("hk_storage") or ""
	net = flt(item.get("hk_net_weight_g")) or (own.get(top, {}).get("unit_weight") * factor if top in own else 0)
	settings = frappe.get_cached_doc(SETTINGS)
	allergens = ld.allergens_for(codes, item_allergens, order)
	barcode, barcode_error = _item_barcode(item)
	content = {
		"item": item_code,
		"code": item_code,
		"title": (item.get("hk_label_title") or item.item_name or item_code).strip(),
		"maker": [l.strip() for l in (settings.maker_lines or "").splitlines() if l.strip()],
		"origin": (settings.origin_line or "").strip(),
		"factory": (settings.factory_statement or "").strip(),
		"ingredients": ld.ingredients_text(rows),
		"ingredient_rows": rows,
		"allergens": allergens,
		"contains": ld.contains_sentence([phrase.get(a, a.lower()) for a in allergens]),
		"storage_key": storage_key,
		"storage": ld.STORAGE_TEXT.get(storage_key, ""),
		"note": (item.get("hk_label_note") or settings.default_note or "").strip(),
		"barcode": barcode,
		"barcode_error": barcode_error,
		"net_weight_g": round(net, 1) if net else 0,
		"shelf_life_days": cint(spec.get("shelf_life_days")) or cint(item.shelf_life_in_days),
		"units_per_label": max(1, cint(item.get("hk_units_per_label")) or 1),
		"recipe_item": top if top in own else None,
		"oem_spec": spec.get("name"),
		"unchecked_allergens": sorted(c for c in codes if c in meta and not meta[c].hk_allergens_checked),
		"no_weight": sorted({w.split(":", 1)[1] for w in warnings if w.startswith("no-weight:")}),
	}
	content["signature"] = ld.content_signature(content)
	return content


def _item_barcode(item) -> tuple[dict | None, str]:
	"""The first row of the Item's Barcodes table, and why it can't print (if so)."""
	rows = [b for b in item.get("barcodes") or [] if b.barcode]
	if not rows:
		return None, ""
	code = {"type": rows[0].barcode_type or "", "value": rows[0].barcode.strip()}
	try:
		lr.barcode_modules(code["type"], code["value"])
	except Exception as e:
		return code, str(e) or "invalid barcode"
	return code, ""


def _piece_grams(lines) -> dict[str, float]:
	"""Grams per piece for ingredients counted in pieces: the Item's weight per
	unit, else the weight typed on a recipe line."""
	out = {}
	for i in frappe.get_all("Item", filters={"weight_per_unit": (">", 0)}, fields=["name", "weight_per_unit", "weight_uom"]):
		uom = (i.weight_uom or "Gram").lower()
		out[i.name] = flt(i.weight_per_unit) * (1000 if uom in ("kg", "kilogram") else 1)
	for rows in lines.values():
		for l in rows:
			if flt(l.grams_per_piece) and l.item not in out:
				out[l.item] = flt(l.grams_per_piece)
	return out


def label_state(item_code: str, content: dict | None = None) -> dict:
	content = content or label_content(item_code)
	checked, signature = frappe.db.get_value("Item", item_code, ["hk_label_checked", "hk_label_signature"])
	missing = ld.missing_for_approval(content)
	if not cint(checked):
		state = "Not checked"
	elif signature != content["signature"]:
		state = "Changed since check"
	else:
		state = "Checked"
	return {"state": state, "ready": state == "Checked", "missing": missing}


def _content_and_state(item_code: str, customer: str | None) -> tuple[dict, dict]:
	"""What prints for this customer, and whether the product's label is checked.
	The check is per product; a client's approved OEM Spec Sheet may replace the
	shelf life and storage, and counts as checked by itself."""
	base = label_content(item_code)
	state = label_state(item_code, base)
	content = label_content(item_code, customer) if _oem_spec(customer, item_code) else base
	return content, state


def production_lot(item_code: str | None, made_on) -> str:
	"""Lot of the production run that made this item on that day; blank when none was logged."""
	if not item_code:
		return ""
	rows = frappe.db.sql(
		"""select i.lot_no from `tabRecipe Production Log Item` i
		join `tabRecipe Production Log` l on l.name = i.parent
		join `tabRecipe` r on r.name = i.recipe
		where l.docstatus = 1 and l.posting_date = %s and r.item = %s and coalesce(i.lot_no, '') != ''
		order by l.creation desc limit 1""",
		(getdate(made_on), item_code),
	)
	return rows[0][0] if rows else ""


def printable(content: dict, units: int, made_on, banner: str = "") -> dict:
	dates = ld.label_dates(getdate(made_on), content.get("shelf_life_days") or 0)
	storage = content.get("storage")
	return {
		**{k: content.get(k) for k in ("title", "ingredients", "contains", "note", "factory", "maker", "origin", "barcode")},
		"net": ld.net_text(content.get("net_weight_g") or 0, content.get("units_per_label") or 1, units),
		"storage": f"Storage : {storage}" if storage else "",
		"best_before": ld.fmt_date(dates["best_before"]),
		"lot": (production_lot(content.get("item"), made_on) or dates["lot"]) if dates["best_before"] else "",
		"banner": banner,
	}


KITCHEN_KINDS = ("Opened", "Batch")


def _kitchen_lines(content: dict) -> list[tuple[str, str]]:
	return [(a, b) for a, b in content.get("lines") or []]


def _printer_size(printer: str | None) -> tuple[float, float, int]:
	if printer and frappe.db.exists("Label Printer", printer):
		p = frappe.db.get_value("Label Printer", printer, ["width_mm", "height_mm", "dpi"], as_dict=True)
		return flt(p.width_mm) or 100, flt(p.height_mm) or 150, cint(p.dpi) or 203
	return 100, 150, 203


# ------------------------------------------------------------------- desk API --

@frappe.whitelist()
def item_label_preview(item_code: str):
	frappe.has_permission("Item", "read", item_code, throw=True)
	content = label_content(item_code)
	state = label_state(item_code, content)
	w, h, dpi = _printer_size(frappe.db.get_single_value(SETTINGS, "default_printer"))
	img = lr.render(printable(content, content["units_per_label"], nowdate(), banner="PREVIEW"), w, h, dpi)
	return {
		"png": lr.to_png_b64(img),
		"state": state,
		"content": {k: content[k] for k in ("title", "ingredients", "allergens", "storage", "shelf_life_days",
		                                    "net_weight_g", "units_per_label", "ingredient_rows", "recipe_item",
		                                    "oem_spec", "unchecked_allergens", "no_weight")},
		"can_check": bool(set(frappe.get_roles()) & set(CHECK_ROLES)),
	}


@frappe.whitelist(methods=["POST"])
def mark_label_checked(item_code: str):
	if not set(frappe.get_roles()) & set(CHECK_ROLES):
		frappe.throw(_("Only a manager can mark a label as checked."), frappe.PermissionError)
	content = label_content(item_code)
	missing = ld.missing_for_approval(content)
	if missing:
		frappe.throw("<br>".join(missing), title=_("Label not ready"))
	frappe.db.set_value("Item", item_code, {
		"hk_label_checked": 1,
		"hk_label_signature": content["signature"],
		"hk_label_checked_by": frappe.session.user,
		"hk_label_checked_on": now_datetime(),
	})
	released = release_jobs(item_code)
	return {"released": released}


def release_jobs(item_code: str) -> int:
	"""Waiting jobs for this item go to the printer once its label is checked."""
	n = 0
	for name in frappe.get_all("Label Job", filters={"item": item_code, "status": "Needs check"}, pluck="name"):
		job = frappe.get_doc("Label Job", name)
		content, state = _content_and_state(item_code, job.customer)
		if state["ready"]:
			job.label_json = json.dumps(content, default=str)
			job.status = "Queued"
			job.hold_reason = ""
			job.save(ignore_permissions=True)
			n += 1
	return n


@frappe.whitelist()
def suggest_allergens(item_code: str) -> list[str]:
	frappe.has_permission("Item", "read", item_code, throw=True)
	name, label_name = frappe.db.get_value("Item", item_code, ["item_name", "hk_label_name"])
	keywords = {
		a.name: [w.strip() for w in (a.keywords or "").splitlines() if w.strip()]
		for a in frappe.get_all("Allergen", filters={"disabled": 0}, fields=["name", "keywords"], order_by="sort_order asc")
	}
	return ld.suggest_allergens(f"{name} {label_name or ''}", keywords)


@frappe.whitelist()
def job_preview(job: str):
	doc = frappe.get_doc("Label Job", job)
	doc.check_permission("read")
	content = json.loads(doc.label_json or "{}") or label_content(doc.item, doc.customer)
	if doc.kind in KITCHEN_KINDS:
		w, h, dpi = _printer_size(doc.printer)
		return {"png": lr.to_png_b64(lr.render_kitchen(_kitchen_lines(content), w, h, dpi)), "labels": cint(doc.label_count) or 1}
	qtys = ld.label_quantities(doc.qty, content.get("units_per_label") or 1)
	w, h, dpi = _printer_size(doc.printer)
	made_on = doc.made_on or _made_on(doc)
	img = lr.render(printable(content, qtys[0] if qtys else 0, made_on), w, h, dpi)
	return {"png": lr.to_png_b64(img), "labels": len(qtys)}


@frappe.whitelist()
def sales_order_labels(sales_order: str):
	frappe.has_permission("Sales Order", "read", sales_order, throw=True)
	return frappe.get_all(
		"Label Job", filters={"sales_order": sales_order},
		fields=["name", "item", "item_name", "qty", "label_count", "status", "hold_reason", "printed_at", "so_detail"],
		order_by="creation asc",
	)


@frappe.whitelist(methods=["POST"])
def queue_sales_order(sales_order: str, rows: str | list | None = None):
	"""Print labels again (or for the first time) for some lines of an order.
	rows: [{"so_detail": ..., "qty": units}]; empty = every line, full quantity."""
	so = frappe.get_doc("Sales Order", sales_order)
	so.check_permission("read")
	if so.docstatus != 1:
		frappe.throw(_("Submit the sales order first."))
	if isinstance(rows, str):
		rows = json.loads(rows or "[]")
	wanted = {r["so_detail"]: flt(r.get("qty")) for r in rows or []}
	made = []
	for line in so.items:
		if wanted and line.name not in wanted:
			continue
		job = make_job(so, line, wanted.get(line.name) or None)
		if job:
			made.append(job.name)
	return made


@frappe.whitelist(methods=["POST"])
def reprint(job: str):
	doc = frappe.get_doc("Label Job", job)
	doc.check_permission("write")
	if doc.status == "Needs check":
		frappe.throw(_("This label is waiting for its product to be checked."))
	doc.status = "Queued"
	doc.error = ""
	doc.save()
	return doc.status


@frappe.whitelist(methods=["POST"])
def print_test_label(printer: str):
	frappe.has_permission("Label Printer", "read", printer, throw=True)
	job = frappe.get_doc({
		"doctype": "Label Job",
		"item": None,
		"item_name": "Test label",
		"qty": 1,
		"label_count": 1,
		"printer": printer,
		"is_test": 1,
		"status": "Queued",
		"label_json": json.dumps({
			"title": "Test label - " + (frappe.defaults.get_global_default("company") or "label printer"),
			"code": "TEST",
			"ingredients": "If you can read this, the Raspberry Pi and the printer are working. "
			               "Check that nothing is cut off at the edges.",
			"allergens": [],
			"storage": "",
			"units_per_label": 1,
			"shelf_life_days": 3,
			"maker": [l for l in (frappe.db.get_single_value(SETTINGS, "maker_lines") or "").splitlines() if l],
			"origin": frappe.db.get_single_value(SETTINGS, "origin_line") or "",
			"barcode": {"type": "CODE-39", "value": "TEST123"},
		}),
	}).insert()
	return job.name


# --------------------------------------------------------------- order hooks --

def make_job(so, line, qty: float | None = None):
	if cint(frappe.db.get_value("Item", line.item_code, "hk_no_label")):
		return None
	content, state = _content_and_state(line.item_code, so.customer)
	units = qty if qty is not None else flt(line.stock_qty) or flt(line.qty)
	job = frappe.get_doc({
		"doctype": "Label Job",
		"sales_order": so.name,
		"so_detail": line.name,
		"customer": so.customer,
		"item": line.item_code,
		"item_name": line.item_name,
		"delivery_date": line.delivery_date or so.delivery_date,
		"qty": units,
		"label_count": len(ld.label_quantities(units, content["units_per_label"])),
		"printer": frappe.db.get_single_value(SETTINGS, "default_printer"),
		"status": "Queued" if state["ready"] else "Needs check",
		"hold_reason": "" if state["ready"] else "; ".join([state["state"]] + state["missing"])[:1000],
		"label_json": json.dumps(content, default=str),
	})
	job.insert(ignore_permissions=True)
	return job


def on_sales_order_submit(doc, method=None):
	if not cint(frappe.db.get_single_value(SETTINGS, "create_on_submit")):
		return
	# Labels are optional: jobs are made quietly, never with a message on submit.
	for line in doc.items:
		make_job(doc, line)


def on_sales_order_cancel(doc, method=None):
	for name in frappe.get_all("Label Job", filters={"sales_order": doc.name, "status": ("in", ("Queued", "Needs check", "Failed"))}, pluck="name"):
		frappe.db.set_value("Label Job", name, "status", "Cancelled")


# ---------------------------------------------------------------- Pi agent ----

def _agent_printer(printer: str):
	if not frappe.db.exists("Label Printer", printer):
		frappe.throw(_("Unknown label printer {0}").format(printer), frappe.DoesNotExistError)
	p = frappe.get_doc("Label Printer", printer)
	roles = set(frappe.get_roles())
	if "System Manager" not in roles:
		if AGENT_ROLE not in roles or (p.api_user and p.api_user != frappe.session.user):
			frappe.throw(_("Not allowed"), frappe.PermissionError)
	return p


def _made_on(job) -> str:
	basis = frappe.db.get_single_value(SETTINGS, "date_basis") or "Print date"
	if basis == "Delivery date" and job.delivery_date:
		return str(job.delivery_date)
	return nowdate()


@frappe.whitelist(methods=["POST"])
def agent_poll(printer: str, agent_version: str | None = None, host: str | None = None,
               ready: int | str = 1, problem: str | None = None):
	"""Called by the Pi every few seconds: records that it is online and hands
	over the next job, already turned into printer data. A Pi that can't reach
	its printer (ready=0) only reports in."""
	p = _agent_printer(printer)
	frappe.db.set_value("Label Printer", p.name, {
		"last_seen": now_datetime(), "agent_version": (agent_version or "")[:40], "agent_host": (host or "")[:80],
		"agent_problem": (problem or "")[:140],
	}, update_modified=False)
	if not cint(ready) or not cint(p.enabled):
		frappe.db.commit()
		return {"job": None}

	cutoff = add_to_date(now_datetime(), minutes=-STUCK_MINUTES)
	for name in frappe.get_all("Label Job", filters={"status": "Printing", "printer": p.name, "claimed_at": ("<", cutoff)}, pluck="name"):
		frappe.db.set_value("Label Job", name, {"status": "Failed", "error": "The printer did not confirm this job."})

	default = frappe.db.get_single_value(SETTINGS, "default_printer")
	rows = frappe.db.sql(
		"""select name from `tabLabel Job`
		where status = 'Queued' and (printer = %(p)s or (coalesce(printer, '') = '' and %(p)s = %(d)s))
		order by creation asc limit 1 for update""",
		{"p": p.name, "d": default or ""},
	)
	if not rows:
		frappe.db.commit()
		return {"job": None}
	job = frappe.get_doc("Label Job", rows[0][0])
	content = json.loads(job.label_json or "{}")
	made_on = _made_on(job)
	if job.kind in KITCHEN_KINDS:
		return _kitchen_job(job, content, p)
	qtys = ld.label_quantities(job.qty, content.get("units_per_label") or 1) or [0]
	banner = "TEST LABEL" if job.is_test else ""
	w, h, dpi = flt(p.width_mm) or 100, flt(p.height_mm) or 150, cint(p.dpi) or 203

	labels = []
	for units in sorted(set(qtys), key=qtys.index):  # one picture per different quantity
		img = lr.for_printer(lr.render(printable(content, units, made_on, banner), w, h, dpi), w, h)
		copies = qtys.count(units)
		if p.mode == "PNG (CUPS)":
			labels.append({"png": lr.to_png_b64(img), "copies": copies})
		else:
			labels.append({"zpl": lr.to_zpl(img, copies), "copies": copies})

	dates = ld.label_dates(getdate(made_on), content.get("shelf_life_days") or 0)
	job.db_set({
		"status": "Printing", "claimed_at": now_datetime(), "printer": p.name, "attempts": cint(job.attempts) + 1,
		"made_on": dates["made_on"], "best_before": dates["best_before"], "lot": dates["lot"],
		"label_count": len(qtys), "error": "",
	})
	frappe.db.commit()
	return {"job": job.name, "format": "png" if p.mode == "PNG (CUPS)" else "zpl", "labels": labels, "count": len(qtys)}


def _kitchen_job(job, content: dict, p) -> dict:
	"""Opened and Batch labels: one small picture, printed `label_count` times."""
	w, h, dpi = flt(p.width_mm) or 50, flt(p.height_mm) or 30, cint(p.dpi) or 203
	copies = max(1, cint(job.label_count) or cint(job.qty))
	img = lr.for_printer(lr.render_kitchen(_kitchen_lines(content), w, h, dpi), w, h)
	label = {"png": lr.to_png_b64(img), "copies": copies} if p.mode == "PNG (CUPS)" else {"zpl": lr.to_zpl(img, copies), "copies": copies}
	job.db_set({"status": "Printing", "claimed_at": now_datetime(), "printer": p.name, "attempts": cint(job.attempts) + 1, "error": ""})
	frappe.db.commit()
	return {"job": job.name, "format": "png" if p.mode == "PNG (CUPS)" else "zpl", "labels": [label], "count": copies}


@frappe.whitelist(methods=["POST"])
def agent_done(printer: str, job: str, ok: int | str = 1, error: str | None = None):
	p = _agent_printer(printer)
	doc = frappe.get_doc("Label Job", job)
	if doc.printer != p.name:
		frappe.throw(_("This job belongs to another printer."), frappe.PermissionError)
	if cint(ok):
		doc.db_set({"status": "Printed", "printed_at": now_datetime(), "error": ""})
	else:
		doc.db_set({"status": "Failed", "error": (error or "Printer error")[:1000]})
	return doc.status


def printer_online(last_seen) -> bool:
	return bool(last_seen) and (now_datetime() - frappe.utils.get_datetime(last_seen)).total_seconds() < ONLINE_SECONDS


@frappe.whitelist()
def printer_status(printer: str):
	frappe.has_permission("Label Printer", "read", printer, throw=True)
	p = frappe.db.get_value("Label Printer", printer, ["last_seen", "agent_version", "agent_host", "agent_problem", "enabled"], as_dict=True)
	waiting = frappe.db.count("Label Job", {"status": "Queued"})
	return {**p, "online": printer_online(p.last_seen), "queued": waiting}
