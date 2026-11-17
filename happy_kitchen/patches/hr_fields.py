"""HR Phase 1: Employee file fields. ID, MPF member number and bank details are pay-level
(permlevel 1: HR Manager / System Manager only)."""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter
from frappe.permissions import add_permission, update_permission_property

from happy_kitchen.hk_operations.hr_rules import CONTRACT_TYPES
from happy_kitchen.hk_operations.team import MANAGER_ROLES

FIELDS = {
	"Employee": [
		{"fieldname": "hk_hr_section", "label": "Hong Kong HR", "fieldtype": "Section Break", "collapsible": 1,
		 "insert_after": "hk_continuous_status"},
		{"fieldname": "hk_contract_type", "label": "Contract Type", "fieldtype": "Select",
		 "options": "\n" + "\n".join(CONTRACT_TYPES), "insert_after": "hk_hr_section"},
		{"fieldname": "hk_nationality", "label": "Nationality", "fieldtype": "Data", "insert_after": "hk_contract_type"},
		{"fieldname": "hk_visa_expiry", "label": "Visa Expiry", "fieldtype": "Date", "insert_after": "hk_nationality",
		 "description": "Visa or work permit. A reminder shows on Today 30 days before."},
		{"fieldname": "hk_probation_end", "label": "Probation Ends", "fieldtype": "Date", "insert_after": "hk_visa_expiry"},
		{"fieldname": "hk_hr_col", "fieldtype": "Column Break", "insert_after": "hk_probation_end"},
		{"fieldname": "hk_id_number", "label": "HKID / Passport No.", "fieldtype": "Data", "permlevel": 1,
		 "insert_after": "hk_hr_col"},
		{"fieldname": "hk_mpf_scheme", "label": "MPF Scheme", "fieldtype": "Data", "permlevel": 1,
		 "insert_after": "hk_id_number"},
		{"fieldname": "hk_mpf_member_no", "label": "MPF Member No.", "fieldtype": "Data", "permlevel": 1,
		 "insert_after": "hk_mpf_scheme", "description": "Blank = not enrolled yet."},
		{"fieldname": "hk_mpf_enrol_due", "label": "MPF Enrolment Due", "fieldtype": "Date", "read_only": 1,
		 "no_copy": 1, "permlevel": 1, "insert_after": "hk_mpf_member_no",
		 "description": "60 days after the joining date. Worked out by the system."},
		{"fieldname": "hk_entitlements", "label": "Entitlements Today", "fieldtype": "Small Text", "read_only": 1,
		 "no_copy": 1, "insert_after": "hk_probation_end",
		 "description": "What applies today under the Employment Ordinance. Worked out by the system."},
	],
}


def execute():
	create_custom_fields(FIELDS, update=True)
	# the standard bank fields hold pay data too
	for field in ("bank_name", "bank_ac_no", "iban"):
		make_property_setter("Employee", field, "permlevel", 1, "Int")
	for role in MANAGER_ROLES:
		add_permission("Employee", role, 1)
		update_permission_property("Employee", role, 1, "write", 1)
