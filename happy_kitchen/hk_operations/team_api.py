"""Server side of the Team pages: Employee labour cost, clock-in PINs and the kiosk, and the
roster grid. Rules and data live in hk_operations/team.py (unit-tested)."""

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, now_datetime, nowdate

from happy_kitchen.hk_operations import team

PIN_TRIES = 5
PIN_LOCK_SECONDS = 300


def _require_roles(roles):
	if not set(roles) & set(frappe.get_roles()):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


# ------------------------------------------------------------------ Employee hooks


def employee_validate(doc, method=None):
	doc.hk_hourly_cost = team.hourly_cost(doc.hk_monthly_base, doc.hk_working_days, doc.hk_hours_per_day, doc.hk_hourly_rate)
	if not doc.get("leave_approver") and frappe.db.exists("User", team.LEAVE_APPROVER):
		doc.leave_approver = team.LEAVE_APPROVER


def employee_on_update(doc, method=None):
	"""Keep the employee's "Kitchen Labour" Activity Cost equal to their hourly cost."""
	if not frappe.db.exists("Activity Type", team.LABOUR_ACTIVITY):
		return
	rate = flt(doc.hk_hourly_cost)
	name = frappe.db.get_value("Activity Cost", {"employee": doc.name, "activity_type": team.LABOUR_ACTIVITY})
	if name:
		if flt(frappe.db.get_value("Activity Cost", name, "costing_rate")) != rate:
			frappe.db.set_value("Activity Cost", name, "costing_rate", rate)
	elif rate:
		frappe.get_doc({"doctype": "Activity Cost", "employee": doc.name, "activity_type": team.LABOUR_ACTIVITY,
		                "costing_rate": rate, "billing_rate": 0}).insert(ignore_permissions=True)


# ------------------------------------------------------------------ PIN and kiosk


@frappe.whitelist(methods=["POST"])
def set_clock_pin(employee: str, pin: str) -> None:
	"""Stores SHA-256("<employee>:<pin>"), never the PIN. HR only."""
	_require_roles(team.MANAGER_ROLES + ["HR User"])
	frappe.has_permission("Employee", "write", employee, throw=True)
	if not team.valid_pin(pin):
		frappe.throw(_("The PIN must be exactly 4 digits."))
	frappe.db.set_value("Employee", employee, "hk_pin_hash", team.pin_hash(employee, pin))


def _kiosk_roles():
	_require_roles(team.MANAGER_ROLES + [team.TABLET_ROLE])


def _last_logs(day) -> dict:
	out = {}
	for c in frappe.get_all("Employee Checkin", filters={"time": (">=", f"{day} 00:00:00")},
	                        fields=["employee", "log_type", "time"], order_by="time asc"):
		out[c.employee] = c
	return out


@frappe.whitelist()
def kiosk_status() -> list[dict]:
	"""Tiles for the clock-in tablet: who is on, their shift today and last check-in. No pay
	fields and no PIN hashes leave the server."""
	_kiosk_roles()
	day = nowdate()
	shifts = {s.employee: s.shift_type for s in frappe.get_all(
		"Shift Assignment", filters={"docstatus": 1, "status": "Active", "start_date": ("<=", day), "end_date": (">=", day)},
		fields=["employee", "shift_type"])}
	logs = _last_logs(day)
	rows = []
	for e in frappe.get_all("Employee", filters={"status": "Active"},
	                        fields=["name", "employee_name", "hk_short_name", "hk_pin_hash"], order_by="hk_short_name asc"):
		last = logs.get(e.name)
		rows.append({
			"name": e.name, "label": e.hk_short_name or e.employee_name, "has_pin": bool(e.hk_pin_hash),
			"shift": shifts.get(e.name), "last_log_type": last.log_type if last else None,
			"last_time": str(last.time) if last else None,
		})
	return rows


@frappe.whitelist(methods=["POST"])
def clock_in(employee: str, pin: str) -> dict:
	"""Checks the PIN and records an Employee Checkin (IN, or OUT after an IN today)."""
	_kiosk_roles()
	lock_key = f"hk_pin_tries:{employee}"
	tries = int(frappe.cache.get_value(lock_key) or 0)
	if tries >= PIN_TRIES:
		frappe.throw(_("Too many wrong PINs. Wait 5 minutes or ask your manager."), title=_("Locked"))
	stored = frappe.db.get_value("Employee", {"name": employee, "status": "Active"}, "hk_pin_hash")
	if not stored or not team.valid_pin(pin) or team.pin_hash(employee, pin) != stored:
		frappe.cache.set_value(lock_key, tries + 1, expires_in_sec=PIN_LOCK_SECONDS)
		return {"ok": False}
	frappe.cache.delete_value(lock_key)
	last = _last_logs(nowdate()).get(employee)
	log_type = team.next_log_type(last.log_type if last else None)
	time = now_datetime()
	frappe.get_doc({"doctype": "Employee Checkin", "employee": employee, "log_type": log_type,
	                "time": time, "device_id": "Kitchen tablet"}).insert(ignore_permissions=True)
	return {"ok": True, "log_type": log_type, "time": str(time)}


# ------------------------------------------------------------------ roster


def _day_assignment(employee: str, day):
	return frappe.db.get_value("Shift Assignment", {"employee": employee, "docstatus": 1, "status": "Active",
	                                                "start_date": day, "end_date": day}, ["name", "shift_type"], as_dict=True)


def _assign(employee: str, day, shift: str, company: str) -> str:
	sa = frappe.get_doc({"doctype": "Shift Assignment", "employee": employee, "shift_type": shift, "company": company,
	                     "start_date": day, "end_date": day, "status": "Active"})
	sa.insert()
	sa.submit()
	return sa.name


@frappe.whitelist(methods=["POST"])
def roster_cycle(employee: str, date: str) -> dict:
	"""One roster tap: Off -> Early -> Late -> Off, as one-day Shift Assignments."""
	frappe.has_permission("Shift Assignment", "create", throw=True)
	day = getdate(date)
	cur = _day_assignment(employee, day)
	nxt = team.next_shift(cur.shift_type if cur else None)
	if cur:
		sa = frappe.get_doc("Shift Assignment", cur.name)
		sa.cancel()
		frappe.delete_doc("Shift Assignment", sa.name)
	name = None
	if nxt:
		company = frappe.db.get_value("Employee", employee, "company") or frappe.defaults.get_global_default("company")
		name = _assign(employee, day, nxt, company)
	return {"shift": nxt, "name": name}


@frappe.whitelist(methods=["POST"])
def roster_copy_week(week_start: str) -> int:
	"""Copies last week's shifts into this week's empty days (skips approved time off)."""
	frappe.has_permission("Shift Assignment", "create", throw=True)
	start = getdate(week_start)
	prev = add_days(start, -7)
	copied = 0
	for s in frappe.get_all("Shift Assignment", filters={"docstatus": 1, "status": "Active",
	                        "start_date": ("between", [prev, add_days(prev, 6)])},
	                        fields=["employee", "shift_type", "start_date", "end_date", "company"]):
		if s.start_date != s.end_date:
			continue
		day = add_days(s.start_date, 7)
		if _day_assignment(s.employee, day) or frappe.db.exists("Leave Application", {
			"employee": s.employee, "docstatus": 1, "status": "Approved", "from_date": ("<=", day), "to_date": (">=", day)}):
			continue
		_assign(s.employee, day, s.shift_type, s.company)
		copied += 1
	return copied


@frappe.whitelist()
def labour_cost_summary(date: str | None = None) -> dict:
	"""Planned labour cost from the roster for a day and its week (Mon-Sun), for the home page
	card. Managers only, because it reveals pay."""
	_require_roles(team.MANAGER_ROLES)
	day = getdate(date or nowdate())
	week_start = add_days(day, -day.weekday())
	hours = {name: team.shift_hours(*team.SHIFT_TYPES[name][:2]) for name in team.SHIFT_TYPES}
	cost = {e.name: flt(e.hk_hourly_cost) for e in frappe.get_all("Employee", filters={"status": "Active"},
	                                                                 fields=["name", "hk_hourly_cost"])}
	today = week = 0.0
	today_hours = 0.0
	for s in frappe.get_all("Shift Assignment", filters={"docstatus": 1, "status": "Active",
	                        "start_date": ("between", [week_start, add_days(week_start, 6)])},
	                        fields=["employee", "shift_type", "start_date"]):
		if s.employee not in cost:
			continue
		h = hours.get(s.shift_type, 0)
		week += h * cost[s.employee]
		if getdate(s.start_date) == day:
			today += h * cost[s.employee]
			today_hours += h
	return {"date": str(day), "planned_today": round(today, 2), "hours_today": today_hours, "planned_week": round(week, 2)}
