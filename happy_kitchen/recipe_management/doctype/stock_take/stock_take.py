# Copyright (c) 2026, Happy Kitchen and contributors
# For license information, please see license.txt

"""A dated count of every active ingredient on a Stock Take Sheet.

Draft -> Submitted -> Approved (locked, docstatus 1), or Submitted -> back to
Draft with a rejection comment. Only a user with the Stock Take Approver role
who did not submit the count can approve or reject it. Approved counts feed the
Inventory Variance report and, if enabled in Recipe Settings, update ERPNext
stock through a Stock Reconciliation.
"""

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, now_datetime

from happy_kitchen.recipe_management import costing
from happy_kitchen.recipe_management.pricing import get_ingredient_prices, get_settings, get_working_recipe
from happy_kitchen.recipe_management.variance import (
	APPROVED,
	DRAFT,
	SUBMITTED,
	VarianceError,
	check_transition,
	compact_packs,
	count_to_stock_qty,
	fit_count_uom,
	packs_to_stock_qty,
)

EDITABLE = (DRAFT,)
# Pack size n lives in pack_uom / pack_factor / counted_packs (n=1) and pack_uom_n ... (n=2, 3)
PACK_FIELDS = [("pack_uom", "pack_factor", "counted_packs")] + [
	(f"pack_uom_{n}", f"pack_factor_{n}", f"counted_packs_{n}") for n in (2, 3)
]


def pack_slots(row) -> list[tuple]:
	"""[(fields, uom, factor)] for the pack sizes set on a sheet or count row."""
	return [(f, row.get(f[0]), row.get(f[1])) for f in PACK_FIELDS if row.get(f[0])]


class StockTake(Document):
	def before_validate(self):
		if not self.company and self.stock_take_sheet:
			self.company = frappe.db.get_value("Stock Take Sheet", self.stock_take_sheet, "company")

	def before_insert(self):
		self.status = DRAFT
		if not self.items:
			self.load_sheet()

	def load_sheet(self):
		sheet = frappe.get_doc("Stock Take Sheet", self.stock_take_sheet)
		self.company = self.company or sheet.company
		for row in sheet.items:
			if not row.active:
				continue
			item = frappe.get_cached_value("Item", row.item, ["stock_uom", "weight_per_unit", "weight_uom", "disabled"], as_dict=True)
			if not item or item.disabled:
				continue
			gpp = costing.grams_per_piece(item.weight_per_unit, item.weight_uom)
			values = {
				"item": row.item,
				"item_name": row.item_name,
				"storage_area": row.storage_area,
				"count_uom": fit_count_uom(row.count_uom, item.stock_uom, gpp),
				"stock_uom": item.stock_uom,
				"grams_per_piece": gpp,
			}
			for (uom_f, factor_f, _), uom in zip(PACK_FIELDS, compact_packs(row.get(f[0]) for f in PACK_FIELDS)):
				values[uom_f], values[factor_f] = uom, pack_factor(row.item, uom)
			self.append("items", values)
		if not self.items:
			frappe.throw(_("The sheet {0} has no active ingredients").format(self.stock_take_sheet))

	def validate(self):
		if self.docstatus == 0 and not self.is_new() and not self.flags.hk_transition:
			before = self.get_doc_before_save()
			if before and before.status == SUBMITTED:
				frappe.throw(_("This count is waiting for approval and can't be changed. Ask an approver to reject it first."))
		for row in self.items:
			self.set_stock_qty(row)
		self.total_rows = len(self.items)
		self.counted_rows = sum(1 for r in self.items if r.counted)

	@staticmethod
	def set_stock_qty(row):
		if not cint(row.counted):
			row.stock_qty = 0
			return
		try:
			packs = [(row.get(f[2]), factor) for f, _, factor in pack_slots(row)]
			if packs:
				row.stock_qty = packs_to_stock_qty(packs, row.counted_qty, row.count_uom, row.stock_uom, row.grams_per_piece)
			else:
				row.stock_qty = count_to_stock_qty(row.counted_qty, row.count_uom, row.stock_uom, row.grams_per_piece)
		except VarianceError as e:
			frappe.throw(_("{0}: {1}").format(row.item_name or row.item, e))

	def before_submit(self):
		# the standard Submit button must not bypass the approval rules
		if not self.flags.hk_approving:
			frappe.throw(_("Use Approve to approve a stock take."))

	def on_submit(self):
		if cint(sync_enabled()):
			self.make_stock_reconciliation()

	def before_cancel(self):
		frappe.throw(_("An approved stock take is locked."))

	def set_valuation_rates(self):
		for row in self.items:
			row.valuation_rate = unit_cost(row.item, row.storage_area)

	def make_stock_reconciliation(self):
		sr = frappe.new_doc("Stock Reconciliation")
		sr.company = self.company
		sr.purpose = "Stock Reconciliation"
		if not frappe.db.exists("Stock Ledger Entry", {"company": self.company, "is_cancelled": 0}):
			# the very first stock posting is an opening entry, booked against the
			# temporary opening (balance sheet) account instead of stock adjustment
			sr.purpose = "Opening Stock"
			sr.expense_account = frappe.db.get_value(
				"Account", {"company": self.company, "account_type": "Temporary", "is_group": 0}, "name"
			)
		sr.posting_date = self.posting_date
		sr.posting_time = self.posting_time
		sr.set_posting_time = 1
		for row in self.items:
			sr.append(
				"items",
				{
					"item_code": row.item,
					"warehouse": row.storage_area,
					"qty": flt(row.stock_qty, 6),
					"valuation_rate": flt(row.valuation_rate, 6),
					"allow_zero_valuation_rate": 0 if flt(row.valuation_rate) else 1,
				},
			)
		sr.remarks = _("From approved Stock Take {0}").format(self.name)
		sr.flags.ignore_permissions = True
		try:
			sr.insert()
		except frappe.ValidationError as e:
			if "None of the items have any change" in str(e):
				return  # ERPNext stock already matches the count
			raise
		sr.submit()
		self.db_set("stock_reconciliation", sr.name)


def pack_factor(item_code: str, pack_uom: str) -> float:
	"""Stock units in one pack, from the Item's UOM Conversion table."""
	return flt(frappe.db.get_value("UOM Conversion Detail", {"parent": item_code, "uom": pack_uom}, "conversion_factor"))


def sync_enabled() -> int:
	if not frappe.db.exists("Singles", {"doctype": "Recipe Settings", "field": "stock_take_sync_stock"}):
		return 1  # default on
	return cint(frappe.db.get_single_value("Recipe Settings", "stock_take_sync_stock"))


def unit_cost(item_code: str, warehouse: str | None = None) -> float:
	"""Cost per stock UOM: ERPNext valuation in that warehouse, else the
	cheapest buying price, else the batch preparation's recipe cost."""
	if warehouse:
		rate = frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "valuation_rate")
		if flt(rate):
			return flt(rate)
	price = costing.pick_price(get_ingredient_prices(item_code))
	if price and flt(price.price_per_base_unit):
		return flt(price.price_per_base_unit)
	working = get_working_recipe(item_code)
	return flt(working.cost_per_unit) if working else 0.0


def _get(name: str, perm: str = "read") -> "StockTake":
	doc = frappe.get_doc("Stock Take", name)
	doc.check_permission(perm)
	return doc


def _transition(doc, action: str, comment: str | None = None) -> str:
	try:
		return check_transition(action, doc.status, frappe.session.user, doc.submitted_by, frappe.get_roles(), comment)
	except VarianceError as e:
		frappe.throw(str(e), title=_("Not allowed"))


@frappe.whitelist()
def make_stock_take(sheet: str, posting_date: str | None = None) -> str:
	doc = frappe.new_doc("Stock Take")
	doc.stock_take_sheet = sheet
	if posting_date:
		doc.posting_date = posting_date
	doc.insert()
	return doc.name


@frappe.whitelist()
def get_count_sheet(name: str) -> dict:
	"""Everything the count screen needs, rows in sheet order."""
	doc = _get(name)
	return {
		"name": doc.name,
		"sheet": doc.stock_take_sheet,
		"posting_date": str(doc.posting_date),
		"status": doc.status,
		"docstatus": doc.docstatus,
		"editable": doc.docstatus == 0 and doc.status in EDITABLE and frappe.has_permission("Stock Take", "write", doc),
		"rejection_comment": doc.rejection_comment if doc.status == DRAFT else None,
		"submitted_by": doc.submitted_by,
		"modified": str(doc.modified),
		"rows": [
			{
				"row": r.name,
				"item": r.item,
				"item_name": r.item_name,
				"storage_area": r.storage_area,
				"count_uom": r.count_uom,
				"packs": [{"uom": uom, "factor": factor} for _, uom, factor in pack_slots(r)],
				"stock_uom": r.stock_uom,
				"counted": cint(r.counted),
				"counted_qty": r.counted_qty if cint(r.counted) else None,
				"counted_packs": [r.get(f[2]) for f, _, _ in pack_slots(r)] if cint(r.counted) else None,
			}
			for r in doc.items
		],
	}


@frappe.whitelist(methods=["POST"])
def save_counts(name: str, counts) -> dict:
	"""Autosave from the count screen: [{"row": child name, "qty": number or null,
	"packs": [number or null per pack size] (a single number from older screens means pack size 1)}].
	Writes each row directly, so two iPads counting different areas don't
	overwrite each other."""
	if isinstance(counts, str):
		counts = json.loads(counts)
	doc = _get(name, "write")
	if doc.docstatus != 0 or doc.status not in EDITABLE:
		frappe.throw(_("This count is {0} and can't be changed.").format(doc.status))
	rows = {r.name: r for r in doc.items}
	saved = []
	now = now_datetime()
	for c in counts or []:
		row = rows.get(c.get("row"))
		if not row:
			continue
		qty, packs = c.get("qty"), c.get("packs")
		if not isinstance(packs, list):
			packs = [packs]
		packs = (packs + [None] * len(PACK_FIELDS))[: len(PACK_FIELDS)]
		if qty in (None, "") and all(p in (None, "") for p in packs):
			values = {"counted": 0, "counted_qty": 0, "stock_qty": 0, "counted_by": None, "counted_at": None}
			values.update({f[2]: 0 for f in PACK_FIELDS})
		else:
			qty, packs = flt(qty), [flt(p) for p in packs]
			if qty < 0 or min(packs) < 0:
				frappe.throw(_("{0}: a count can't be negative").format(row.item_name))
			values = {"counted": 1, "counted_qty": qty}
			values.update({f[2]: n if row.get(f[0]) else 0 for f, n in zip(PACK_FIELDS, packs)})
			row.update(values)
			StockTake.set_stock_qty(row)
			values.update({"stock_qty": row.stock_qty, "counted_by": frappe.session.user, "counted_at": now})
		frappe.db.set_value("Stock Take Item", row.name, values, update_modified=False)
		saved.append(row.name)
	counted = frappe.db.count("Stock Take Item", {"parent": name, "parenttype": "Stock Take", "counted": 1})
	frappe.db.set_value("Stock Take", name, "counted_rows", counted)
	return {"saved": saved, "counted_rows": counted, "total_rows": len(doc.items)}


@frappe.whitelist(methods=["POST"])
def submit_for_approval(name: str) -> str:
	doc = _get(name, "write")
	missing = [r.item_name for r in doc.items if not cint(r.counted)]
	if missing:
		frappe.throw(
			_("{0} ingredients have no count yet (enter 0 if there is none): {1}").format(
				len(missing), ", ".join(missing[:10]) + ("..." if len(missing) > 10 else "")
			)
		)
	doc.status = _transition(doc, "submit")
	doc.submitted_by, doc.submitted_on = frappe.session.user, now_datetime()
	doc.flags.hk_transition = True
	doc.save()
	return doc.status


@frappe.whitelist(methods=["POST"])
def approve(name: str) -> str:
	doc = _get(name)
	doc.status = _transition(doc, "approve")
	doc.approved_by, doc.approved_on = frappe.session.user, now_datetime()
	doc.set_valuation_rates()
	doc.flags.hk_transition = doc.flags.hk_approving = True
	doc.submit()  # needs the submit permission, which only the approver role has
	return doc.status


@frappe.whitelist(methods=["POST"])
def reject(name: str, comment: str) -> str:
	doc = _get(name)
	doc.status = _transition(doc, "reject", comment)
	doc.rejected_by, doc.rejected_on, doc.rejection_comment = frappe.session.user, now_datetime(), comment.strip()
	doc.flags.hk_transition = True
	doc.flags.ignore_permissions = True  # approvers may lack write; the role check above is the gate
	doc.save()
	doc.add_comment("Comment", _("Rejected: {0}").format(comment.strip()))
	return doc.status
