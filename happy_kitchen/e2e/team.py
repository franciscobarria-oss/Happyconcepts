"""P12: labour cost on save, clock-in PIN and kiosk, roster tap, overtime approval. Rolled back."""

import frappe
from frappe.utils import add_days, flt, nowdate

from happy_kitchen.hk_operations import team, team_api

P = "E2E-P12-"


def _check(cond, msg):
	if not cond:
		raise AssertionError(msg)


def run():
	frappe.set_user("Administrator")
	company = frappe.defaults.get_global_default("company")
	abbr = frappe.db.get_value("Company", company, "abbr")
	emp = None
	try:
		_check(frappe.db.exists("Shift Type", "Early") and frappe.db.exists("Shift Type", "Late"), "shift types seeded")
		_check(frappe.db.count("Overtime Rate") >= 3, "overtime rates seeded")
		_check(frappe.db.exists("Department", f"Sweet - {abbr}"), "departments seeded")

		# a live site already has employees: move the naming series past the highest one (rolled back with the rest)
		numbers = [int(n.rsplit("-", 1)[-1]) for n in frappe.get_all("Employee", pluck="name") if n.rsplit("-", 1)[-1].isdigit()]
		if numbers:
			frappe.db.sql("insert into `tabSeries` (name, current) values ('HR-EMP-', %s) "
			              "on duplicate key update current = greatest(current, %s)", (max(numbers), max(numbers)))
		emp = frappe.get_doc({
			"doctype": "Employee", "first_name": P + "Ah", "last_name": "Chan", "gender": "Female",
			"date_of_birth": "1990-01-01", "date_of_joining": "2024-01-01", "company": company, "status": "Active",
			"department": f"Sweet - {abbr}", "hk_short_name": P + "Ah",
			"hk_monthly_base": 20000, "hk_working_days": 24, "hk_hours_per_day": 9,
			"hk_default_overtime_rate": "Time and a half",
		}).insert()
		expected = team.hourly_cost(20000, 24, 9)
		_check(flt(emp.hk_hourly_cost) == expected, f"hourly cost {emp.hk_hourly_cost} != {expected}")
		ac = frappe.db.get_value("Activity Cost", {"employee": emp.name, "activity_type": team.LABOUR_ACTIVITY}, "costing_rate")
		_check(flt(ac) == expected, f"Activity Cost Kitchen Labour synced: {ac}")
		emp.hk_monthly_base = 40000
		emp.save()
		_check(flt(frappe.db.get_value("Activity Cost", {"employee": emp.name, "activity_type": team.LABOUR_ACTIVITY},
		                                "costing_rate")) == team.hourly_cost(40000, 24, 9), "Activity Cost follows a pay change")

		# PIN: stored as a hash, checked on the server, never sent to the kiosk
		team_api.set_clock_pin(emp.name, "4321")
		_check(frappe.db.get_value("Employee", emp.name, "hk_pin_hash") == team.pin_hash(emp.name, "4321"), "PIN hash stored")
		tile = next(r for r in team_api.kiosk_status() if r["name"] == emp.name)
		_check(tile["has_pin"] and "hk_pin_hash" not in tile, "kiosk sees has_pin only")
		_check(team_api.clock_in(emp.name, "0000") == {"ok": False}, "wrong PIN refused")
		r = team_api.clock_in(emp.name, "4321")
		_check(r["ok"] and r["log_type"] == "IN", f"clock in: {r}")
		_check(team_api.clock_in(emp.name, "4321")["log_type"] == "OUT", "second tap clocks out")
		_check(frappe.db.count("Employee Checkin", {"employee": emp.name}) == 2, "two check-ins")

		# roster: Off -> Early -> Late -> Off on one day
		day = add_days(nowdate(), 3)
		_check(team_api.roster_cycle(emp.name, day)["shift"] == "Early", "first tap = Early")
		_check(frappe.db.get_value("Shift Assignment", {"employee": emp.name, "start_date": day, "docstatus": 1},
		                           "shift_type") == "Early", "submitted Shift Assignment")
		_check(team_api.roster_cycle(emp.name, day)["shift"] == "Late", "second tap = Late")
		_check(team_api.roster_cycle(emp.name, day)["shift"] is None, "third tap = Off")
		_check(not frappe.db.exists("Shift Assignment", {"employee": emp.name, "start_date": day, "docstatus": 1}),
		       "no active shift left")

		# overtime: submit = approve, 1.5 x own wage
		ot = frappe.get_doc({"doctype": "Overtime Entry", "employee": emp.name, "date": nowdate(), "hours": 2,
		                     "company": company}).insert()
		_check(ot.overtime_rate == "Time and a half", "default rate from the employee")
		ot.submit()
		ot.reload()
		_check(ot.status == "Approved" and ot.approved_by == "Administrator", "approved on submit")
		_check(abs(flt(ot.amount) - round(2 * 40000 / 216 * 1.5, 2)) < 0.01, f"amount {ot.amount}")
		print("ok: team e2e passed")
	finally:
		frappe.db.rollback()
		if emp:
			frappe.cache.delete_value(f"hk_pin_tries:{emp.name}")  # Redis isn't rolled back
		frappe.clear_cache()
