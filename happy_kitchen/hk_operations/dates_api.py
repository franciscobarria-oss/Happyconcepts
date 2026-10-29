"""Batches, opened items and kitchen date labels (P15b): lots for production runs,
the Opened screen, batch labels, and the Use-by list on Today."""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, get_datetime, getdate, now_datetime, nowdate

from happy_kitchen.hk_operations import date_labels as dl
from happy_kitchen.hk_operations import dates
from happy_kitchen.recipe_management.production import BATCH_PREPARATION

SETTINGS = "Label Settings"
KITCHEN_USE = "Kitchen date labels"
PRODUCT_TYPE = "Finished Product"
BATCH_ROLES = ("System Manager", "Stock Manager", "Manufacturing Manager", "Manufacturing User", "Stock User", "Kitchen Tablet")
LOOKBACK_DAYS = 14
WASTE_REASON = "Spoiled / Expired"


# ------------------------------------------------------------------ helpers --

def date_printer() -> str | None:
	"""The printer for kitchen date labels: the one named in Label Settings, else the
	first enabled printer set to "Kitchen date labels"."""
	named = frappe.db.get_single_value(SETTINGS, "date_label_printer")
	if named and frappe.db.get_value("Label Printer", named, "enabled"):
		return named
	rows = frappe.get_all("Label Printer", filters={"enabled": 1, "label_use": KITCHEN_USE}, pluck="name", order_by="creation asc", limit=1)
	return rows[0] if rows else None


def allergens_for(item_code: str) -> list[tuple[str, str]]:
	"""(English, 中文) allergens: from the item's own recipe when it has one, else its Item Allergen rows."""
	names: list[str] = []
	try:
		from happy_kitchen.hk_operations import labels
		names = list(labels.label_content(item_code).get("allergens") or [])
	except Exception:
		frappe.clear_last_message()
		names = []
	if not names:
		names = frappe.get_all("Item Allergen", filters={"parenttype": "Item", "parent": item_code}, pluck="allergen")
	zh = dict(frappe.get_all("Allergen", filters={"name": ("in", names or [""])}, fields=["name", "allergen_zh"], as_list=True))
	return [(n, zh.get(n) or "") for n in dict.fromkeys(names)]


def _name_zh(item_code: str) -> str:
	return frappe.db.get_value("Item", item_code, "hk_item_name_zh") or ""


def queue_kitchen_labels(kind: str, content: dict, labels: int = 1, **links) -> str | None:
	"""Put one Label Job on the date printer's queue; None when there is no such printer."""
	printer = date_printer()
	if not printer:
		return None
	job = frappe.get_doc({
		"doctype": "Label Job",
		"kind": kind,
		"item": content.get("item"),
		"item_name": content.get("item_name"),
		"qty": max(1, cint(labels)),
		"label_count": max(1, cint(labels)),
		"printer": printer,
		"status": "Queued",
		"label_json": json.dumps({"lines": dl.kitchen_lines({**content, "kind": kind})}, default=str, ensure_ascii=False),
		**links,
	})
	job.insert(ignore_permissions=True)
	return job.name


def can_handle_dates() -> bool:
	return bool(set(frappe.get_roles()) & set(BATCH_ROLES))


def _require_kitchen_user():
	if not can_handle_dates():
		frappe.throw(_("Not allowed"), frappe.PermissionError)


# ------------------------------------------------------------- Opened screen --

@frappe.whitelist()
def find_item(code: str) -> dict | None:
	"""A scanned barcode or typed item code: the item, how long it keeps once opened, and recent lots."""
	_require_kitchen_user()
	code = (code or "").strip()
	if not code:
		return None
	item = frappe.db.get_value("Item", code, "name") or frappe.db.get_value("Item Barcode", {"barcode": code}, "parent")
	if not item:
		return None
	row = frappe.db.get_value(
		"Item", item,
		["name", "item_name", "stock_uom", "hk_open_life_value", "hk_open_life_unit", "hk_open_storage", "has_batch_no"], as_dict=True,
	)
	row["open_life_set"] = flt(row.hk_open_life_value) > 0
	row["lots"] = recent_lots(item)
	return row


def recent_lots(item: str) -> list[dict]:
	"""Lots from recent production logs, newest first (ERPNext batch where one exists)."""
	since = add_days(nowdate(), -60)
	return frappe.db.sql(
		"""select i.lot_no as lot, i.batch_no, i.use_by, l.posting_date
		from `tabRecipe Production Log Item` i join `tabRecipe Production Log` l on l.name = i.parent
		where l.docstatus = 1 and i.lot_no is not null and i.lot_no != ''
		and l.posting_date >= %s and i.recipe in (select name from `tabRecipe` where item = %s)
		order by l.posting_date desc, l.creation desc limit 8""",
		(since, item), as_dict=True,
	)


@frappe.whitelist(methods=["POST"])
def open_item(item: str, labels: int | str = 1, batch_no: str | None = None, lot: str | None = None) -> dict:
	"""Record an opened item and, when labels > 0, queue its small label (optional)."""
	_require_kitchen_user()
	frappe.has_permission("Opened Item", "create", throw=True)
	if flt(frappe.db.get_value("Item", item, "hk_open_life_value")) <= 0:
		frappe.throw(_("Set 'Expiry after opening' on item {0} first (Label tab).").format(item))
	doc = frappe.get_doc({
		"doctype": "Opened Item", "item": item, "batch_no": batch_no or None, "lot": lot or "",
		"labels": max(0, cint(labels)), "status": "Open",
	})
	doc.insert()
	if doc.labels:
		doc.db_set("label_job", print_opened_label(doc.name, doc.labels))
	doc.reload()
	return {"name": doc.name, "use_by": doc.use_by, "label_job": doc.label_job, "printer": date_printer()}


def opened_content(doc) -> dict:
	return {
		"item": doc.item, "item_name": doc.item_name, "item_name_zh": _name_zh(doc.item),
		"start": get_datetime(doc.opened_at), "use_by": get_datetime(doc.use_by) if doc.use_by else None,
		"storage": doc.storage, "allergens": allergens_for(doc.item),
		"by": frappe.db.get_value("User", doc.opened_by, "full_name") or doc.opened_by, "lot": doc.lot,
	}


@frappe.whitelist(methods=["POST"])
def print_opened_label(name: str, labels: int | str = 1) -> str | None:
	doc = frappe.get_doc("Opened Item", name)
	doc.check_permission("read")
	job = queue_kitchen_labels(dl.OPENED, opened_content(doc), cint(labels) or 1, opened_item=doc.name)
	if not job:
		frappe.msgprint(_("No kitchen label printer is set up (Label Printer > Use = Kitchen date labels)."), indicator="orange")
	return job


# ---------------------------------------------------------- production batches --

def _row_kind(recipe_type: str | None) -> str | None:
	return recipe_type if recipe_type in (BATCH_PREPARATION, PRODUCT_TYPE) else None


def assign_batches(log) -> None:
	"""Give each batch-preparation and product row a lot and a use-by date; make an
	ERPNext Batch for it when the item already tracks batches. Runs on submit."""
	types = dict(frappe.get_all("Recipe", filters={"name": ("in", list({r.recipe for r in log.items}))},
	                            fields=["name", "recipe_type"], as_list=True))
	made_on = getdate(log.posting_date)
	taken = set(frappe.get_all("Recipe Production Log Item", filters={"lot_no": ("like", "L" + made_on.strftime("%y%m%d") + "%")}, pluck="lot_no"))
	for row in log.items:
		if not _row_kind(types.get(row.recipe)):
			continue
		item = frappe.db.get_value("Recipe", row.recipe, "item")
		life = cint(frappe.db.get_value("Item", item, "shelf_life_in_days"))
		lot = dates.next_lot(made_on, taken)
		taken.add(lot)
		use_by = dates.batch_use_by(made_on, life)
		row.db_set({"lot_no": lot, "use_by": use_by})
		if cint(frappe.db.get_value("Item", item, "has_batch_no")):
			batch_id = f"{item}-{lot}"
			if frappe.db.exists("Batch", batch_id):
				batch_id = f"{batch_id}-{log.name}"
			frappe.get_doc({
				"doctype": "Batch", "batch_id": batch_id, "item": item, "manufacturing_date": made_on,
				"expiry_date": use_by, "reference_doctype": "Recipe Production Log", "reference_name": log.name,
			}).insert(ignore_permissions=True)
			row.db_set("batch_no", batch_id)


def queue_batch_labels_on_submit(log) -> list[str]:
	if not cint(frappe.db.get_single_value(SETTINGS, "batch_labels_on_submit")):
		return []
	return _queue_batch_labels(log, [r for r in log.items if r.lot_no], 1)


def _queue_batch_labels(log, rows, labels: int) -> list[str]:
	jobs = []
	for row in rows:
		item = frappe.db.get_value("Recipe", row.recipe, "item")
		item_name, storage = frappe.db.get_value("Item", item, ["item_name", "hk_open_storage"])
		content = {
			"item": item, "item_name": item_name, "item_name_zh": _name_zh(item), "start": getdate(log.posting_date),
			"use_by": getdate(row.use_by) if row.use_by else None, "storage": storage or "",
			"allergens": allergens_for(item), "lot": row.lot_no,
			"by": frappe.db.get_value("User", log.owner, "full_name") or log.owner,
		}
		job = queue_kitchen_labels(dl.BATCH, content, labels, production_log=log.name)
		if job:
			jobs.append(job)
	return jobs


@frappe.whitelist(methods=["POST"])
def print_batch_labels(log: str, rows: str | list | None = None, labels: int | str = 1) -> list[str]:
	"""The "Print batch labels" button. rows: row names; empty = every row with a lot."""
	doc = frappe.get_doc("Recipe Production Log", log)
	doc.check_permission("read")
	if doc.docstatus != 1:
		frappe.throw(_("Submit the Production Log first"))
	if isinstance(rows, str):
		rows = json.loads(rows or "[]")
	chosen = [r for r in doc.items if r.lot_no and (not rows or r.name in rows)]
	if not chosen:
		frappe.throw(_("No row in this log has a lot (only batch preparations and products do)."))
	jobs = _queue_batch_labels(doc, chosen, cint(labels) or 1)
	if not jobs:
		frappe.msgprint(_("No kitchen label printer is set up (Label Printer > Use = Kitchen date labels)."), indicator="orange")
	return jobs


# ------------------------------------------------------------------ Today list --

def _default_uom(item: str) -> str:
	from happy_kitchen.recipe_management import variance
	return variance.default_count_uom(frappe.db.get_value("Item", item, "stock_uom"))


def expiring() -> list[dict]:
	"""Opened items and production batches that are past use-by or end today or tomorrow."""
	now = now_datetime()
	horizon = get_datetime(add_days(nowdate(), 1) + " 23:59:59")
	out = []
	for o in frappe.get_all("Opened Item", filters={"status": "Open", "use_by": ("<=", horizon)},
	                        fields=["name", "item", "item_name", "use_by", "lot", "storage"], order_by="use_by asc", limit=50):
		out.append({"kind": "Opened Item", "name": o.name, "row": "", "item": o.item, "item_name": o.item_name, "lot": o.lot,
		            "use_by": str(o.use_by), "state": dates.date_state(get_datetime(o.use_by), now), "label": dates.fmt_when(get_datetime(o.use_by))})
	since = add_days(nowdate(), -LOOKBACK_DAYS)
	rows = frappe.db.sql(
		"""select i.name as row, l.name, r.item, i.lot_no as lot, i.use_by, i.batch_no
		from `tabRecipe Production Log Item` i
		join `tabRecipe Production Log` l on l.name = i.parent
		join `tabRecipe` r on r.name = i.recipe
		where l.docstatus = 1 and i.use_by is not null and i.use_by <= %s and l.posting_date >= %s
		and coalesce(i.date_status, '') = '' order by i.use_by asc limit 50""",
		(add_days(nowdate(), 1), since), as_dict=True,
	)
	for r in rows:
		if r.batch_no:
			left = frappe.db.get_value("Batch", r.batch_no, "batch_qty")
			if left is not None and flt(left) <= 0:
				continue
		item_name = frappe.db.get_value("Item", r.item, "item_name")
		out.append({"kind": "Recipe Production Log", "name": r.name, "row": r.row, "item": r.item, "item_name": item_name, "lot": r.lot,
		            "use_by": str(r.use_by), "state": dates.date_state(getdate(r.use_by), now), "label": dates.fmt_when(getdate(r.use_by))})
	out.sort(key=lambda x: x["use_by"])
	for x in out:
		x["uom"] = _default_uom(x["item"])
	return out


@frappe.whitelist(methods=["POST"])
def close(kind: str, name: str, row: str | None = None, action: str = "Used up", qty: float | str | None = None, uom: str | None = None) -> dict:
	"""Used up just closes the line. Discarded also writes a Wastage Log line (qty and uom needed)."""
	if action not in ("Used up", "Discarded"):
		frappe.throw(_("Unknown action"))
	if kind == "Opened Item":
		doc = frappe.get_doc("Opened Item", name)
		item = doc.item
	elif kind == "Recipe Production Log":
		doc = frappe.get_doc("Recipe Production Log", name)
		line = next((r for r in doc.items if r.name == row), None)
		if not line:
			frappe.throw(_("Row not found"))
		item = frappe.db.get_value("Recipe", line.recipe, "item")
	else:
		frappe.throw(_("Unknown kind"))
	doc.check_permission("write" if kind == "Opened Item" else "read")
	result = {}
	if action == "Discarded":
		if flt(qty) <= 0 or not uom:
			frappe.throw(_("Enter how much was thrown away."))
		from happy_kitchen.recipe_management import kitchen
		result = kitchen.log_wastage(
			[{"item": item, "qty": flt(qty), "uom": uom, "reason": WASTE_REASON, "notes": f"{kind} {name}"}]
		)
	if kind == "Opened Item":
		doc.db_set({"status": action, "closed_at": now_datetime(), "wastage_log": result.get("name")})
	else:
		line.db_set({"date_status": action, "wastage_log": result.get("name")})
	return {"wastage_log": result.get("name")}
