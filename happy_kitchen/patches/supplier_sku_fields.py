import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

FIELDS = {
	"Item": [
		{"fieldname": "hk_supplier_skus", "label": "Supplier SKUs", "fieldtype": "Small Text",
		 "insert_after": "supplier_items", "read_only": 1,
		 "description": "Filled from the Supplier Items table above so the item is found by any supplier's SKU."},
	],
}


def execute():
	"""Supplier SKUs: Item search finds an item by a supplier's part number as well as by our SKU (the item code)."""
	create_custom_fields(FIELDS, update=True)
	current = frappe.get_meta("Item").search_fields or ""
	fields = [f.strip() for f in current.split(",") if f.strip()]
	if "hk_supplier_skus" not in fields:
		fields.append("hk_supplier_skus")
		make_property_setter("Item", None, "search_fields", ",".join(fields), "Data", for_doctype=True)
	# existing items: fill the search text once
	from happy_kitchen.hk_operations import sku

	for parent in frappe.get_all("Item Supplier", filters={"parenttype": "Item"}, pluck="parent", distinct=True):
		rows = frappe.get_all("Item Supplier", filters={"parent": parent, "parenttype": "Item"},
		                      fields=["supplier", "supplier_part_no"])
		frappe.db.set_value("Item", parent, "hk_supplier_skus", sku.search_text(rows), update_modified=False)
