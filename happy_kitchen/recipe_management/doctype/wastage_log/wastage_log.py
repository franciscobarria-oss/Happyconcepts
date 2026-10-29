# Copyright (c) 2026, Happy Kitchen and contributors
# For license information, please see license.txt

"""Waste logged in the kitchen: item, quantity and reason. Submitting takes it
out of stock (a Material Issue from the item's storage area) and the Inventory
Variance report shows it as recorded wastage, separate from unexplained loss.

If stock can't be issued (e.g. the system shows less on hand than was wasted),
the log still submits: the waste is recorded and the problem is noted on the
log for the office, instead of blocking the kitchen."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from happy_kitchen.recipe_management import costing
from happy_kitchen.recipe_management.production import stock_qty
from happy_kitchen.recipe_management.variance import VarianceError, count_to_stock_qty, default_count_uom


class WastageLog(Document):
	def validate(self):
		self.logged_by = self.logged_by or frappe.session.user
		company = frappe.defaults.get_global_default("company")
		self.total_cost = 0
		for row in self.items:
			if flt(row.qty) <= 0:
				frappe.throw(_("Row {0}: quantity must be more than 0").format(row.idx))
			item = frappe.get_cached_value("Item", row.item, ["stock_uom", "weight_per_unit", "weight_uom", "item_name"], as_dict=True)
			row.item_name = item.item_name
			row.stock_uom = item.stock_uom
			row.uom = row.uom or default_count_uom(item.stock_uom)
			row.warehouse = row.warehouse or frappe.db.get_value(
				"Item Default", {"parent": row.item, "company": company}, "default_warehouse"
			)
			try:
				row.stock_qty = count_to_stock_qty(
					row.qty, row.uom, item.stock_uom, costing.grams_per_piece(item.weight_per_unit, item.weight_uom)
				)
			except VarianceError as e:
				frappe.throw(_("Row {0} ({1}): {2}").format(row.idx, item.item_name, e))
			from happy_kitchen.recipe_management.doctype.stock_take.stock_take import unit_cost

			row.valuation_rate = unit_cost(row.item, row.warehouse)
			row.amount = flt(row.stock_qty) * flt(row.valuation_rate)
			self.total_cost += row.amount

	def on_submit(self):
		self.issue_stock()

	def on_cancel(self):
		if self.stock_entry and frappe.db.get_value("Stock Entry", self.stock_entry, "docstatus") == 1:
			frappe.get_doc("Stock Entry", self.stock_entry).cancel()

	def issue_stock(self):
		company = frappe.defaults.get_global_default("company")
		se = frappe.new_doc("Stock Entry")
		se.stock_entry_type = "Material Issue"
		se.purpose = "Material Issue"
		se.company = company
		se.posting_date, se.posting_time, se.set_posting_time = self.posting_date, self.posting_time, 1
		se.remarks = _("Wastage {0}").format(self.name)
		for row in self.items:
			if not row.warehouse:
				continue
			qty = stock_qty(row.stock_qty, bool(frappe.get_cached_value("UOM", row.stock_uom, "must_be_whole_number")))
			se.append("items", {"item_code": row.item, "qty": qty, "uom": row.stock_uom, "stock_uom": row.stock_uom,
			                    "conversion_factor": 1, "s_warehouse": row.warehouse})
		if not se.items:
			self.db_set("stock_note", _("No storage area set on these items, so nothing was taken out of stock."))
			return
		frappe.db.savepoint("hk_wastage_issue")
		try:
			se.insert(ignore_permissions=True)
			se.submit()
			self.db_set("stock_entry", se.name)
			self.db_set("stock_note", None)
		except Exception as e:
			frappe.db.rollback(save_point="hk_wastage_issue")
			frappe.clear_messages()
			self.db_set("stock_note", _("Waste recorded, but stock was not updated: {0}").format(frappe.utils.strip_html(str(e)))[:500])
