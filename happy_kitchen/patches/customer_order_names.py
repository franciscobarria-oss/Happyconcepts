from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

FIELDS = {
	"Customer": [
		{"fieldname": "hk_order_names", "label": "Names in order emails", "fieldtype": "Small Text",
		 "insert_after": "customer_group",
		 "description": "One per line: how this outlet is named on its purchase orders (e.g. W Hong Kong, IKEA Kowloon Bay). Email order pick-up files an order under the customer whose name, one of these names or a shipping address line appears in the email or its PDF."},
	],
}


def execute():
	"""Email orders: names that identify an outlet on its purchase orders (forwarded mail has no customer email)."""
	create_custom_fields(FIELDS, update=True)
