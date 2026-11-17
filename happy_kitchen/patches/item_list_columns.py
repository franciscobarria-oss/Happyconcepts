import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

FIELDS = {
	"Item": [
		{"fieldname": "hk_list_supplier", "label": "Supplier", "fieldtype": "Data", "insert_after": "hk_supplier_skus",
		 "read_only": 1, "in_list_view": 1, "no_copy": 1},
		{"fieldname": "hk_list_price", "label": "Buying Price", "fieldtype": "Data", "insert_after": "hk_list_supplier",
		 "read_only": 1, "in_list_view": 1, "no_copy": 1},
	],
}


def execute():
	"""Supplier and buying price columns on the Item list, filled once here and then kept by Item / Item Price hooks."""
	create_custom_fields(FIELDS, update=True)
	from happy_kitchen.hk_operations.list_price_api import values_for

	for code in frappe.get_all("Item", pluck="name"):
		for k, v in values_for(code).items():
			frappe.db.set_value("Item", code, k, v, update_modified=False)
