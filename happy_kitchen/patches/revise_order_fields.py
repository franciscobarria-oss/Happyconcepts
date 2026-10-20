from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

FIELDS = {
	"Sales Order": [
		{"fieldname": "hk_email_order", "label": "Email Order", "fieldtype": "Link", "options": "Email Order",
		 "insert_after": "customer_name", "read_only": 1, "allow_on_submit": 1, "no_copy": 1,
		 "description": "The email this order was picked up from."},
		{"fieldname": "hk_revision_count", "label": "Revisions", "fieldtype": "Int", "insert_after": "hk_email_order",
		 "read_only": 1, "allow_on_submit": 1, "no_copy": 1, "default": "0"},
		{"fieldname": "hk_needs_review", "label": "Revised: check before delivering", "fieldtype": "Check",
		 "insert_after": "hk_revision_count", "read_only": 1, "allow_on_submit": 1, "no_copy": 1,
		 "in_standard_filter": 1},
	],
}


def execute():
	"""Revise order: flags on the Sales Order. History lives in Order Revision (DocType from its JSON)."""
	create_custom_fields(FIELDS, update=True)
