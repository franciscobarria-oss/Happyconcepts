from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

FIELDS = {
	"Sales Order Item": [
		{"fieldname": "hk_po_rate", "label": "Customer PO price", "fieldtype": "Currency", "options": "currency",
		 "insert_after": "rate", "read_only": 1, "no_copy": 1, "allow_on_submit": 1,
		 "description": "The unit price on the customer's PO (orders picked up from email)."},
	],
}


def execute():
	"""Customer PO price on Sales Order lines, compared with the rate (order_prices.py)."""
	create_custom_fields(FIELDS, update=True)
