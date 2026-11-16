"""Part-timer "468" watch: hours in the last 4 weeks from Employee Checkin, a status on the
Employee, one desk alert per step up, and the Today line. Rules: continuous.py."""

import frappe
from frappe import _
from frappe.utils import add_days, getdate, nowdate

from happy_kitchen.hk_operations import continuous as rules
from happy_kitchen.hk_operations.team import MANAGER_ROLES


def _hourly_staff() -> list:
	return frappe.get_all("Employee", filters={"status": "Active", "hk_hourly_rate": (">", 0)},
	                      fields=["name", "employee_name", "hk_short_name", "hk_monthly_base", "hk_continuous_status"])


def hours_for(employee: str, end=None) -> float:
	end = getdate(end or nowdate())
	rows = frappe.get_all("Employee Checkin", filters={"employee": employee,
	                      "time": (">=", f"{add_days(end, -rules.WINDOW_DAYS - 1)} 00:00:00")},
	                      fields=["log_type", "time"], order_by="time asc")
	return rules.window_hours(rules.shift_hours([(r.log_type, r.time) for r in rows]), end)


def check_all(end=None, notify=True) -> list[dict]:
	"""Updates every hourly employee's status; returns those that moved up."""
	moved = []
	for e in _hourly_staff():
		if e.hk_monthly_base:
			continue
		hours = hours_for(e.name, end)
		status = rules.level(hours)
		if status != (e.hk_continuous_status or rules.BELOW):
			frappe.db.set_value("Employee", e.name, "hk_continuous_status", status, update_modified=False)
		if rules.worsened(e.hk_continuous_status, status):
			moved.append({"employee": e.name, "name": e.hk_short_name or e.employee_name, "hours": hours, "status": status})
	if notify and moved:
		_notify(moved)
	return moved


def _notify(moved):
	users = {u for role in MANAGER_ROLES for u in frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"},
	         pluck="parent") if u not in ("Administrator", "Guest") and frappe.db.get_value("User", u, "enabled")}
	if not users:
		return
	from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification

	for m in moved:
		enqueue_create_notification(list(users), {
			"type": "Alert", "document_type": "Employee", "document_name": m["employee"],
			"subject": rules.message(m["name"], m["hours"], m["status"]),
		})


def scheduled_check():
	"""Daily (hooks.py)."""
	check_all()
	frappe.db.commit()


def waiting_lines() -> list[dict]:
	"""Today > Waiting on you: part-timers close to or past 68 hours in 4 weeks."""
	if not set(MANAGER_ROLES) & set(frappe.get_roles()):
		return []
	out = []
	for e in _hourly_staff():
		if e.hk_monthly_base or (e.hk_continuous_status or rules.BELOW) == rules.BELOW:
			continue
		hours = hours_for(e.name)
		reached = e.hk_continuous_status == rules.REACHED
		out.append({"label": _("Part-timer counts as continuous: {0}").format(e.hk_short_name or e.employee_name) if reached
		            else _("Part-timer close to 68 hours: {0}").format(e.hk_short_name or e.employee_name),
		            "detail": _("{0} of 68 hours in the last 4 weeks").format(f"{hours:g}"),
		            "route": f"Form/Employee/{e.name}", "tone": "warning" if reached else "info"})
	return out
