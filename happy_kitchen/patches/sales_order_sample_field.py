from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

FIELDS = {
	"Sales Order": [
		{"fieldname": "hk_is_sample", "label": "Sample order", "fieldtype": "Check", "insert_after": "po_no",
		 "allow_on_submit": 1, "no_copy": 1, "in_standard_filter": 1,
		 "description": "A sample sent to a customer: no price is needed and it is confirmed without a person checking the value."},
	],
}


def execute():
	"""Sales Order checkbox for sample orders (kept at 0, allowed by auto-confirm)."""
	create_custom_fields(FIELDS, update=True)
