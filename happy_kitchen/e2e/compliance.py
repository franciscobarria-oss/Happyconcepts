"""Kitchen Checks: starting data, due runs, answers, PIN sign-off, overdue -> missed, review.
Creates E2E-* records and always rolls back."""

from datetime import timedelta

import frappe
from frappe.utils import now_datetime

from happy_kitchen.hk_compliance import api, schedule
from happy_kitchen.hk_operations import team_api

P = "E2E-CHK-"


def _check(cond, msg):
	if not cond:
		raise AssertionError(msg)


def run():
	frappe.set_user("Administrator")
	company = frappe.defaults.get_global_default("company")
	try:
		_check(frappe.db.exists("Role", "Compliance Manager"), "Compliance Manager role")
		_check(frappe.db.exists("Checklist Template", "Opening checks"), "starter checklists seeded")
		_check(not frappe.db.get_value("Checklist Schedule", {"template": "Opening checks"}, "active"),
		       "starter schedules start switched off")

		area = frappe.get_doc({"doctype": "Check Area", "area_name": P + "Pastry"}).insert()
		tpl = frappe.get_doc({"doctype": "Checklist Template", "title": P + "Opening", "category": "Opening",
		                      "requires_review": 1, "items": [
			{"prompt": "Sanitiser ready", "answer_type": "Yes/No", "required": 1},
			{"prompt": "Chiller", "answer_type": "Number", "max_value": "5", "unit": "°C", "required": 1, "critical": 1},
			{"prompt": "Notes", "answer_type": "Text", "required": 0},
		]}).insert()
		try:
			frappe.get_doc({"doctype": "Checklist Template", "title": P + "Bad", "category": "Other",
			                "items": [{"prompt": "x", "answer_type": "Number", "min_value": "9", "max_value": "5"}]}).insert()
			raise AssertionError("lowest above highest accepted")
		except frappe.ValidationError:
			pass

		now = now_datetime().replace(second=0, microsecond=0)
		start = now - timedelta(minutes=30)
		sch = frappe.get_doc({"doctype": "Checklist Schedule", "template": tpl.name, "area": area.name,
		                      "frequency": "Daily", "start_time": start.strftime("%H:%M:00"),
		                      "due_time": (now + timedelta(minutes=30)).strftime("%H:%M:00"),
		                      "grace_minutes": 0, "active": 1}).insert()
		if (now + timedelta(minutes=30)).date() != now.date() or start.date() != now.date():
			return print("skipped: too close to midnight")  # window maths around midnight is unit-tested

		# the schedule was switched on before this window opened (active_from is set on switch-on)
		frappe.db.set_value("Checklist Schedule", sch.name, "active_from", start - timedelta(minutes=5))
		made = api.create_due_runs(now, area.name)
		_check(len(made) == 1, f"one run due: {made}")
		_check(api.create_due_runs(now, area.name) == [], "never twice")
		run_name = made[0]
		r = frappe.get_doc("Checklist Run", run_name)
		_check(len(r.answers) == 3 and r.answers[1].max_value == "5", "answers copied from the template")

		tasks = api.today_tasks(area.name)
		_check([x["name"] for x in tasks["due"]] == [run_name], f"tablet shows it as due: {tasks}")

		# employee with a PIN (a live site already has employees: move the naming series past them)
		numbers = [int(n.rsplit("-", 1)[-1]) for n in frappe.get_all("Employee", pluck="name") if n.rsplit("-", 1)[-1].isdigit()]
		if numbers:
			frappe.db.sql("insert into `tabSeries` (name, current) values ('HR-EMP-', %s) "
			              "on duplicate key update current = greatest(current, %s)", (max(numbers), max(numbers)))
		emp = frappe.get_doc({"doctype": "Employee", "first_name": P + "Mei", "gender": "Female",
		                      "date_of_birth": "1990-01-01", "date_of_joining": "2024-01-01", "company": company,
		                      "status": "Active", "hk_short_name": P + "Mei",
		                      "hk_monthly_base": 18000, "hk_working_days": 24, "hk_hours_per_day": 9}).insert()
		team_api.set_clock_pin(emp.name, "2468")

		api.save_answer(run_name, 1, value="Yes")
		res = api.save_answer(run_name, 2, value="8")
		_check(res["result"] == "Fail" and res["status"] == schedule.IN_PROGRESS, f"8 °C fails: {res}")
		out = api.sign_off(run_name, emp.name, "2468")
		_check(not out["ok"] and any("failed" in p for p in out["problems"]), f"needs a corrective action: {out}")
		api.save_answer(run_name, 2, corrective_action="Moved food to the other chiller")
		_check(api.sign_off(run_name, emp.name, "0000") == {"ok": False, "wrong_pin": True}, "wrong PIN refused")
		frappe.cache.delete_value(f"hk_pin_tries:{emp.name}")
		out = api.sign_off(run_name, emp.name, "2468")
		_check(out["ok"] and out["status"] == schedule.WITH_ISSUES and out["issues"] == 1, f"signed with issues: {out}")
		r.reload()
		_check(r.docstatus == 1 and r.employee == emp.name and r.critical_issues == 1, "locked and signed by the employee")
		_check(r.answers[0].answered_by == emp.name, "answers carry who signed")
		try:
			api.save_answer(run_name, 1, value="No")
			raise AssertionError("a signed run accepted a change")
		except frappe.ValidationError:
			pass

		lines = api.waiting_lines()
		_check(any("review" in (x["label"] or "").lower() for x in lines), f"Today asks to review: {lines}")
		_check(api.review([run_name], "ok") == 1, "reviewed")
		_check(frappe.db.get_value("Checklist Run", run_name, "status") == schedule.REVIEWED, "status Reviewed")

		# a run nobody signs: Overdue after the grace, Missed after missed_after_hours
		run2 = api._create_run(frappe._dict(sch.as_dict()), start - timedelta(hours=6), start - timedelta(hours=5),
		                       schedule.run_key(sch.name, start - timedelta(hours=6))).name
		api.refresh_open_statuses(start - timedelta(hours=5) + timedelta(minutes=1))
		_check(frappe.db.get_value("Checklist Run", run2, "status") == schedule.OVERDUE, "overdue")
		became = api.refresh_open_statuses(now)
		_check(frappe.db.get_value("Checklist Run", run2, "status") == schedule.MISSED and run2 not in became,
		       "missed, not notified twice")
		_check(any(run2 == x["name"] for x in api.today_tasks(area.name)["overdue"]), "tablet shows the missed run")

		report = frappe.get_attr("happy_kitchen.hk_compliance.report.kitchen_checks_log.kitchen_checks_log.execute")
		_, rows = report({"area": area.name, "only_problems": 1})
		_check({x.name for x in rows} == {run_name, run2}, f"log shows problems: {[x.name for x in rows]}")
		print("Kitchen Checks e2e: all checks passed")
	finally:
		frappe.db.rollback()
