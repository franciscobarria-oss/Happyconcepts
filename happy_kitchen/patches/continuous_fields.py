from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.permissions import add_permission, update_permission_property

from happy_kitchen.hk_operations.team import MANAGER_ROLES

FIELDS = {
	"Employee": [
		{"fieldname": "hk_continuous_status", "label": "468 Status", "fieldtype": "Data", "read_only": 1,
		 "no_copy": 1, "permlevel": 1, "insert_after": "hk_pin_hash",
		 "description": "Below / Close / Reached: 68 hours in the last 4 weeks (Hong Kong continuous contract). Updated daily."},
	],
}


def execute():
	create_custom_fields(FIELDS, update=True)
	for role in MANAGER_ROLES:
		add_permission("Employee", role, 1)
		update_permission_property("Employee", role, 1, "write", 1)
