from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

FIELDS = {
	"Supplier": [
		{"fieldname": "hk_min_order_amount", "label": "Minimum Order Amount (MOQ)", "fieldtype": "Currency",
		 "insert_after": "payment_terms", "non_negative": 1,
		 "description": "In the company currency (HKD). A Purchase Order below it can be saved but not submitted. 0 = no minimum."},
		{"fieldname": "hk_products_tab", "label": "Products", "fieldtype": "Tab Break",
		 "insert_after": "hk_min_order_amount"},
		{"fieldname": "hk_products_html", "label": "Products", "fieldtype": "HTML",
		 "insert_after": "hk_products_tab"},
	],
	"Item": [
		{"fieldname": "hk_order_multiple", "label": "Order in Multiples Of", "fieldtype": "Float",
		 "insert_after": "min_order_qty", "non_negative": 1,
		 "description": "In the stock UOM, e.g. 12 for eggs by the dozen. Purchase Orders must use a whole multiple. 0 = any quantity."},
	],
}


def execute():
	"""P4: supplier minimum order amount, the Supplier Products tab and Item order multiples."""
	create_custom_fields(FIELDS, update=True)
