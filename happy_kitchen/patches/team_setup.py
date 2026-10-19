import frappe
from frappe.utils import nowdate

from happy_kitchen.hk_operations import team as t


def execute():
	"""P12 starting data: departments, activity types, shifts, holidays, annual leave and
	overtime rates. Idempotent: existing records are left as the team edited them."""
	company = frappe.defaults.get_global_default("company")
	if not company:
		return
	abbr = frappe.db.get_value("Company", company, "abbr")

	for dept in t.DEPARTMENTS:
		if not frappe.db.exists("Department", f"{dept} - {abbr}"):
			frappe.get_doc({"doctype": "Department", "department_name": dept, "company": company,
			                "parent_department": "All Departments"}).insert(ignore_permissions=True)

	if not frappe.db.exists("Activity Type", t.LABOUR_ACTIVITY):
		frappe.get_doc({"doctype": "Activity Type", "activity_type": t.LABOUR_ACTIVITY}).insert(ignore_permissions=True)
	if not frappe.db.exists("Activity Type", t.OVERTIME_ACTIVITY):
		frappe.get_doc({"doctype": "Activity Type", "activity_type": t.OVERTIME_ACTIVITY,
		                "costing_rate": t.OVERTIME_ACTIVITY_RATE}).insert(ignore_permissions=True)

	if not frappe.db.exists("Holiday List", t.HOLIDAY_LIST):
		start, end = t.HOLIDAY_LIST_RANGE
		frappe.get_doc({"doctype": "Holiday List", "holiday_list_name": t.HOLIDAY_LIST, "from_date": start, "to_date": end,
		                "holidays": [{"holiday_date": d, "description": n} for d, n in t.HOLIDAYS.items()]}).insert(
			ignore_permissions=True)
	if not frappe.db.get_value("Company", company, "default_holiday_list"):
		frappe.db.set_value("Company", company, "default_holiday_list", t.HOLIDAY_LIST)

	for name, (start, end, color) in t.SHIFT_TYPES.items():
		if frappe.db.exists("Shift Type", name):
			continue
		frappe.get_doc({
			"doctype": "Shift Type", "name": name, "start_time": start, "end_time": end, "color": color,
			"holiday_list": t.HOLIDAY_LIST, "enable_auto_attendance": 1,
			"determine_check_in_and_check_out": "Strictly based on Log Type in Employee Checkin",
			"working_hours_calculation_based_on": "First Check-in and Last Check-out",
			"begin_check_in_before_shift_start_time": 60, "allow_check_out_after_shift_end_time": 180,
			"mark_auto_attendance_on_holidays": 1, "process_attendance_after": nowdate(),
			"enable_late_entry_marking": 1, "late_entry_grace_period": t.LATE_GRACE_MIN,
			"working_hours_threshold_for_absent": 2,
		}).insert(ignore_permissions=True, set_name=name)

	if not frappe.db.exists("Leave Type", t.ANNUAL_LEAVE):
		frappe.get_doc({"doctype": "Leave Type", "leave_type_name": t.ANNUAL_LEAVE, "is_carry_forward": 1,
		                "include_holiday": 0}).insert(ignore_permissions=True)

	for name, method, value in t.OVERTIME_RATES:
		if not frappe.db.exists("Overtime Rate", name):
			frappe.get_doc({"doctype": "Overtime Rate", "rate_name": name, "method": method, "value": value}).insert(
				ignore_permissions=True)

	# The owner approves time off. Users are never created here; roles are only added if they exist.
	if frappe.db.exists("User", t.LEAVE_APPROVER):
		user = frappe.get_doc("User", t.LEAVE_APPROVER)
		if "Leave Approver" not in {r.role for r in user.roles}:
			user.add_roles("Leave Approver")
