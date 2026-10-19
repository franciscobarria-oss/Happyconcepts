import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

# Starting wastage reasons (English, Traditional Chinese); edit or add more in Wastage Reason.
REASONS = [
	("Spoiled / Expired", "變壞 / 過期"),
	("Overproduction", "生產過剩"),
	("Prep / Cooking Error", "製作失誤"),
	("Dropped / Damaged", "跌落 / 損壞"),
	("Staff Meal", "員工餐"),
	("Tasting / Sample", "試味 / 樣品"),
	("Customer Return", "客戶退貨"),
	("Other", "其他"),
]

FIELDS = {
	"Purchase Receipt": [
		{"fieldname": "hk_has_discrepancy", "label": "Differs from Order", "fieldtype": "Check", "read_only": 1,
		 "insert_after": "supplier_delivery_note", "in_standard_filter": 1, "allow_on_submit": 1, "no_copy": 1},
		{"fieldname": "hk_delivery_flags", "label": "Delivery Check", "fieldtype": "Small Text", "read_only": 1,
		 "insert_after": "hk_has_discrepancy", "allow_on_submit": 1, "no_copy": 1, "depends_on": "hk_has_discrepancy"},
	],
	"Purchase Receipt Item": [
		{"fieldname": "hk_invoice_rate", "label": "Invoice Price", "fieldtype": "Currency", "options": "currency",
		 "insert_after": "rate", "read_only": 1, "allow_on_submit": 1, "no_copy": 1,
		 "description": "Price on the supplier's delivery note / invoice, typed on Receive Delivery. Stock is still received at the PO price."},
	],
}


def execute():
	"""P11: wastage reasons, and the delivery-check fields on Purchase Receipt."""
	for reason, zh in REASONS:
		if not frappe.db.exists("Wastage Reason", reason):
			frappe.get_doc({"doctype": "Wastage Reason", "reason": reason, "reason_zh": zh}).insert(ignore_permissions=True)
	create_custom_fields(FIELDS, update=True)
