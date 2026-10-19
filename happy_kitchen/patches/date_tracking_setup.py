"""P15b: kitchen dates. Expiry after opening on Item (Label tab), a Chinese name for
the small kitchen labels, the Chiller warehouse, and batch labels on by default."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from happy_kitchen.setup import base

ITEM_FIELDS = [
	{"fieldname": "hk_dates_section", "label": "Kitchen date labels", "fieldtype": "Section Break",
	 "insert_after": "hk_label_signature", "collapsible": 0},
	{"fieldname": "hk_item_name_zh", "label": "Chinese name on kitchen labels", "fieldtype": "Data",
	 "insert_after": "hk_dates_section", "description": "Printed under the item name on opened and batch labels."},
	{"fieldname": "hk_open_life_value", "label": "Expiry after opening", "fieldtype": "Float",
	 "insert_after": "hk_item_name_zh",
	 "description": "How long it keeps once opened (or, for a batch preparation, once taken out). Blank = no opened label date."},
	{"fieldname": "hk_open_life_unit", "label": "Unit", "fieldtype": "Select", "options": "Days\nHours", "default": "Days",
	 "insert_after": "hk_open_life_value",
	 "description": "Days count the opening day as day 1 and end at 23:59; hours count from the minute it is opened."},
	{"fieldname": "hk_dates_cb", "fieldtype": "Column Break", "insert_after": "hk_open_life_unit"},
	{"fieldname": "hk_open_storage", "label": "Storage once opened", "fieldtype": "Select",
	 "options": "\nAmbient\nChilled\nFrozen", "insert_after": "hk_dates_cb"},
]


def execute():
	create_custom_fields({"Item": ITEM_FIELDS}, update=True)

	company = frappe.defaults.get_global_default("company")
	if company:
		abbr = frappe.db.get_value("Company", company, "abbr")
		if abbr:
			base.warehouses(company, abbr)  # adds Chiller next to Fridge and Freezer

	if not frappe.db.exists("Singles", {"doctype": "Label Settings", "field": "batch_labels_on_submit"}):
		frappe.db.set_single_value("Label Settings", "batch_labels_on_submit", 1)
