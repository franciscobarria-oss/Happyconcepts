import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from happy_kitchen.hk_operations.current_flag import apply_suffix

HAND_LABEL = "Cur" + "rent"  # the label used when the field was made by hand (not a UI string)

FIELDS = {
	"Item": [
		{"fieldname": "hk_is_current", "label": "Current Purchase", "fieldtype": "Check",
		 "insert_after": "disabled", "default": "0",
		 "description": "Tick the last-purchased version of a repeated item. Its name then ends in (current)."},
	],
}


def execute():
	"""Checkbox on Item for the last-purchased version of repeated items. Items already tagged 'Current'
	(done by hand on 2026-10-22) get the checkbox ticked and the name suffix. Safe to run again."""
	create_custom_fields(FIELDS, update=True)
	_adopt_hand_made_field()
	for name, item_name in frappe.db.sql(
		"select name, item_name from `tabItem` where `_user_tags` like %s", ("%,Current%",)
	):
		frappe.db.set_value("Item", name, {"hk_is_current": 1, "item_name": apply_suffix(item_name, 1)},
		                    update_modified=False)


def _adopt_hand_made_field():
	"""A 'Current' checkbox was first added by hand on hcl-erp (2026-10-22): move its ticks into
	hk_is_current and remove it, so there is one field, installed from code."""
	for cf in frappe.get_all("Custom Field", filters={"dt": "Item", "label": HAND_LABEL, "fieldtype": "Check",
	                                                  "fieldname": ["!=", "hk_is_current"]},
	                         fields=["name", "fieldname"]):
		if frappe.db.has_column("Item", cf.fieldname):
			frappe.db.sql(f"update `tabItem` set hk_is_current = 1 where `{cf.fieldname}` = 1")
		frappe.delete_doc("Custom Field", cf.name, ignore_permissions=True)
