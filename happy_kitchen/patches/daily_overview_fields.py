"""Daily Sales Overview: how a customer shows as a column on the sheet. All optional:
without them the heading and short name come from the customer's name
(see hk_operations/daily_overview.column_for)."""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

FIELDS = {
	"Customer": [
		{"fieldname": "hk_sheet_section", "label": "Daily Sales Overview", "fieldtype": "Section Break",
		 "insert_after": "tax_category", "collapsible": 1},
		{"fieldname": "hk_sheet_group", "label": "Sheet heading", "fieldtype": "Data", "insert_after": "hk_sheet_section",
		 "description": "Customers with the same heading sit together, e.g. IKEA, SODEXO."},
		{"fieldname": "hk_sheet_label", "label": "Sheet column name", "fieldtype": "Data", "insert_after": "hk_sheet_group",
		 "description": "Short outlet name, e.g. CWB."},
		{"fieldname": "hk_sheet_cb", "fieldtype": "Column Break", "insert_after": "hk_sheet_label"},
		{"fieldname": "hk_sheet_label_zh", "label": "Sheet location (Chinese)", "fieldtype": "Data",
		 "insert_after": "hk_sheet_cb", "description": "Printed under the column name, e.g. 銅鑼灣."},
		{"fieldname": "hk_sheet_sort", "label": "Sheet order", "fieldtype": "Int", "insert_after": "hk_sheet_label_zh",
		 "description": "Lower numbers first. Blank = after the numbered ones, by heading and name."},
	],
}


def execute():
	create_custom_fields(FIELDS, update=True)
