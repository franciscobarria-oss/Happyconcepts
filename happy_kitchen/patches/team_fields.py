from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.permissions import add_permission, update_permission_property

from happy_kitchen.hk_operations.team import MANAGER_ROLES

CUR = "Company:company:default_currency"
FIELDS = {
	"Employee": [
		{"fieldname": "hk_labour_cost_section", "label": "Labour Cost", "fieldtype": "Section Break",
		 "insert_after": "designation"},
		{"fieldname": "hk_short_name", "label": "Short Name", "fieldtype": "Data", "in_standard_filter": 1,
		 "insert_after": "hk_labour_cost_section", "description": "Shown on the roster and the clock-in tablet."},
		{"fieldname": "hk_cert_expiry", "label": "Hygiene Cert Expiry", "fieldtype": "Date",
		 "insert_after": "hk_short_name", "description": "Shown on the Team page 30 days before it expires."},
		{"fieldname": "hk_monthly_base", "label": "Monthly Base Salary", "fieldtype": "Currency", "options": CUR,
		 "insert_after": "hk_cert_expiry", "permlevel": 1, "description": "Full-time only. Leave empty for hourly staff."},
		{"fieldname": "hk_hourly_rate", "label": "Hourly Wage", "fieldtype": "Currency", "options": CUR,
		 "insert_after": "hk_monthly_base", "permlevel": 1, "description": "Part-time / hourly staff only."},
		{"fieldname": "hk_cost_col", "fieldtype": "Column Break", "insert_after": "hk_hourly_rate"},
		{"fieldname": "hk_working_days", "label": "Working Days per Month", "fieldtype": "Int", "default": "24",
		 "insert_after": "hk_cost_col", "permlevel": 1},
		{"fieldname": "hk_hours_per_day", "label": "Hours per Day", "fieldtype": "Float", "default": "9",
		 "insert_after": "hk_working_days", "permlevel": 1},
		{"fieldname": "hk_hourly_cost", "label": "Hourly Labour Cost (incl. MPF)", "fieldtype": "Currency",
		 "options": CUR, "insert_after": "hk_hours_per_day", "read_only": 1, "bold": 1, "permlevel": 1,
		 "description": "(Monthly base + employer MPF 5%, capped 1,500) / (days x hours), or hourly wage x 1.05. Recalculated on save."},
		{"fieldname": "hk_default_overtime_rate", "label": "Default Overtime Rate", "fieldtype": "Link",
		 "options": "Overtime Rate", "insert_after": "hk_hourly_cost", "permlevel": 1,
		 "description": "Used when an Overtime Entry is created for this person."},
		{"fieldname": "hk_pin_hash", "label": "Clock-in PIN Hash", "fieldtype": "Data", "hidden": 1, "read_only": 1,
		 "insert_after": "hk_default_overtime_rate", "no_copy": 1, "permlevel": 1},
	],
}


def execute():
	"""P12: Employee labour-cost, cert and clock-in fields. Pay fields are permlevel 1, which
	only HR Manager and System Manager can read or write."""
	create_custom_fields(FIELDS, update=True)
	for role in MANAGER_ROLES:
		add_permission("Employee", role, 1)
		update_permission_property("Employee", role, 1, "write", 1)
