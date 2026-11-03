"""Kitchen Checks server side: creating due runs (15-minute job), the tablet screen
(/app/kitchen-checks), PIN sign-off, manager review and the Today lines. Rules live in the
pure modules schedule.py and scoring.py (unit-tested)."""

import base64
import json

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, get_datetime, getdate, now_datetime, nowdate

from happy_kitchen.hk_compliance import schedule, scoring
from happy_kitchen.hk_compliance.doctype.checklist_run.checklist_run import mark_reviewed, problem_message
from happy_kitchen.hk_compliance.doctype.checklist_schedule.checklist_schedule import as_rule
from happy_kitchen.hk_operations import team_api

MANAGER_ROLES = ("System Manager", "Compliance Manager")
KIOSK_ROLES = MANAGER_ROLES + ("Kitchen Tablet",)
MAX_PHOTO_BYTES = 6 * 1024 * 1024
SCHEDULE_FIELDS = ["name", "template", "area", "department", "frequency", "day_of_month", "start_time", "due_time",
                   "every_hours", "grace_minutes"] + [d.lower() for d in schedule.WEEKDAYS]


def _require(roles):
	if not set(roles) & set(frappe.get_roles()):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def _settings():
	return frappe.get_cached_doc("Compliance Settings")


# ------------------------------------------------------------------ creating runs


def _active_schedules(area=None) -> list:
	filters = {"active": 1}
	if area:
		filters["area"] = area
	rows = frappe.get_all("Checklist Schedule", filters=filters, fields=SCHEDULE_FIELDS)
	live_tpl = set(frappe.get_all("Checklist Template", filters={"active": 1}, pluck="name"))
	live_area = set(frappe.get_all("Check Area", filters={"active": 1}, pluck="name"))
	return [r for r in rows if r.template in live_tpl and r.area in live_area]


def _create_run(sch, start, end, key):
	doc = frappe.get_doc({
		"doctype": "Checklist Run", "template": sch.template, "area": sch.area, "department": sch.department,
		"schedule": sch.name, "run_key": key, "run_date": start.date(), "window_start": start, "window_end": end,
		"grace_minutes": cint(sch.grace_minutes), "status": schedule.PENDING,
	})
	doc.insert(ignore_permissions=True)
	return doc


def create_due_runs(now=None, area=None) -> list[str]:
	"""A run for every schedule window that has started and has none yet (yesterday on)."""
	now = now or now_datetime()
	rows = {r.name: r for r in _active_schedules(area)}
	if not rows:
		return []
	existing = set(frappe.get_all("Checklist Run", filters={
		"schedule": ("in", list(rows)), "window_start": (">=", add_days(now.date(), -2))}, pluck="run_key"))
	made = []
	for r in schedule.runs_to_create({n: as_rule(s) for n, s in rows.items()}, existing, now):
		made.append(_create_run(rows[r["schedule"]], r["window_start"], r["window_end"], r["key"]).name)
	return made


def refresh_open_statuses(now=None) -> list[str]:
	"""Pending / In progress -> Overdue -> Missed. Returns the runs that just became Overdue."""
	now = now or now_datetime()
	missed_after = flt(_settings().missed_after_hours or 4)
	became_overdue = []
	for r in frappe.get_all("Checklist Run", filters={"docstatus": 0, "status": ("in", schedule.OPEN_STATUSES),
	                                                  "window_end": ("is", "set")},
	                        fields=["name", "status", "window_end", "grace_minutes"]):
		started = r.status != schedule.PENDING
		new = schedule.open_status(now, get_datetime(r.window_end), r.grace_minutes, missed_after, started)
		if new == r.status or (r.status in (schedule.OVERDUE, schedule.MISSED) and new in (schedule.PENDING, schedule.IN_PROGRESS)):
			continue
		frappe.db.set_value("Checklist Run", r.name, "status", new, update_modified=False)
		if new == schedule.OVERDUE or (new == schedule.MISSED and r.status != schedule.OVERDUE):
			became_overdue.append(r.name)
	return became_overdue


def _notify_overdue(names):
	if not names or not cint(_settings().notify_overdue):
		return
	users = {u for u in frappe.get_all("Has Role", filters={"role": "Compliance Manager", "parenttype": "User"},
	                                    pluck="parent") if frappe.db.get_value("User", u, "enabled")}
	if not users:
		return
	from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification

	for name in names:
		run = frappe.db.get_value("Checklist Run", name, ["title", "area", "window_end"], as_dict=True)
		enqueue_create_notification(list(users), {
			"type": "Alert", "document_type": "Checklist Run", "document_name": name,
			"subject": _("Overdue: {0} in {1} (due {2})").format(run.title, run.area, str(run.window_end)[11:16]),
		})


def scheduled_runs():
	"""Cron every 15 minutes (hooks.py)."""
	if not cint(_settings().enabled):
		return
	create_due_runs()
	_notify_overdue(refresh_open_statuses())
	frappe.db.commit()


# ------------------------------------------------------------------ tablet screen


@frappe.whitelist()
def areas() -> list[dict]:
	_require(KIOSK_ROLES)
	return frappe.get_all("Check Area", filters={"active": 1}, fields=["name", "area_name_zh", "department"],
	                      order_by="name asc")


def _run_row(r) -> dict:
	return {"name": r.name, "title": r.title, "title_zh": r.get("title_zh"), "category": r.category,
	        "status": r.status, "band": schedule.band(r.status), "window_start": str(r.window_start or ""),
	        "window_end": str(r.window_end or ""), "employee_name": r.employee_name, "signed_at": str(r.signed_at or ""),
	        "late": r.late, "issues": r.issues}


@frappe.whitelist()
def today_tasks(area: str) -> dict:
	"""Runs for the tablet: open ones from the last two days, done ones from today, and today's
	windows that haven't started yet (they can be started early)."""
	_require(KIOSK_ROLES)
	now = now_datetime()
	create_due_runs(now, area)
	refresh_open_statuses(now)
	fields = ["name", "title", "category", "status", "window_start", "window_end", "employee_name", "signed_at",
	          "late", "issues", "schedule", "run_key", "template"]
	open_runs = frappe.get_all("Checklist Run", fields=fields, order_by="window_end asc", filters={
		"area": area, "docstatus": 0, "run_date": (">=", add_days(nowdate(), -1))})
	done = frappe.get_all("Checklist Run", fields=fields, order_by="signed_at desc", filters={
		"area": area, "docstatus": 1, "signed_at": (">=", nowdate())})
	zh = dict(frappe.get_all("Checklist Template", fields=["name", "title_zh"], as_list=True))
	for r in open_runs + done:
		r.title_zh = zh.get(r.template)
	keys = {r.run_key for r in open_runs + done} | set(frappe.get_all(
		"Checklist Run", filters={"area": area, "run_date": nowdate()}, pluck="run_key"))
	later = []
	for s in _active_schedules(area):
		for start, end in schedule.windows(as_rule(s), now.date()):
			key = schedule.run_key(s.name, start)
			if start > now and key not in keys:
				later.append({"schedule": s.name, "title": s.template, "title_zh": zh.get(s.template),
				              "window_start": str(start), "window_end": str(end)})
	later.sort(key=lambda x: x["window_start"])
	return {
		"now": str(now),
		"overdue": [_run_row(r) for r in open_runs if schedule.band(r.status) == "overdue"],
		"due": [_run_row(r) for r in open_runs if schedule.band(r.status) == "due"],
		"later": later,
		"done": [_run_row(r) for r in done],
	}


@frappe.whitelist(methods=["POST"])
def start_early(schedule_name: str, window_start: str) -> str:
	"""Creates the run for a window that hasn't started yet, so it can be done ahead of time."""
	_require(KIOSK_ROLES)
	sch = frappe.get_all("Checklist Schedule", filters={"name": schedule_name, "active": 1}, fields=SCHEDULE_FIELDS)
	if not sch:
		frappe.throw(_("This checklist is no longer scheduled."))
	start = get_datetime(window_start)
	for s, e in schedule.windows(as_rule(sch[0]), start.date()):
		if s == start:
			key = schedule.run_key(schedule_name, s)
			return frappe.db.get_value("Checklist Run", {"run_key": key}) or _create_run(sch[0], s, e, key).name
	frappe.throw(_("No checklist is due at that time."))


def _staff(department=None) -> list[dict]:
	"""Name tiles for sign-off: people on shift today first. No pay fields or PIN hashes."""
	day = nowdate()
	on_shift = set(frappe.get_all("Shift Assignment", filters={
		"docstatus": 1, "status": "Active", "start_date": ("<=", day), "end_date": (">=", day)}, pluck="employee"))
	rows = frappe.get_all("Employee", filters={"status": "Active"},
	                      fields=["name", "employee_name", "hk_short_name", "hk_pin_hash", "department"])
	out = [{"name": e.name, "label": e.hk_short_name or e.employee_name, "has_pin": bool(e.hk_pin_hash),
	        "on_shift": e.name in on_shift, "my_team": bool(department) and e.department == department} for e in rows]
	out.sort(key=lambda e: (not e["on_shift"], not e["my_team"], e["label"].lower()))
	return out


@frappe.whitelist()
def get_run(name: str) -> dict:
	_require(KIOSK_ROLES)
	doc = frappe.get_doc("Checklist Run", name)
	answers = []
	for r in doc.answers:
		d = r.as_dict()
		answers.append({k: d.get(k) for k in ("idx", "prompt", "prompt_zh", "answer_type", "expected", "unit", "help",
		                                      "value", "result", "corrective_action", "note", "photo", "required",
		                                      "photo_required", "critical")}
		               | {"choices": [c for c in (d.choices or "").splitlines() if c.strip()],
		                  "limits": scoring.limits_text(d)})
	presets = frappe.get_all("Corrective Action Preset", fields=["action", "action_zh", "category"], order_by="action asc")
	return {
		"name": doc.name, "title": doc.title,
		"title_zh": frappe.db.get_value("Checklist Template", doc.template, "title_zh"),
		"area": doc.area, "status": doc.status, "docstatus": doc.docstatus, "window_end": str(doc.window_end or ""),
		"employee_name": doc.employee_name, "signed_at": str(doc.signed_at or ""),
		"answers": answers,
		"presets": [p for p in presets if not p.category or p.category == doc.category],
		"staff": _staff(doc.department) if doc.docstatus == 0 else [],
	}


def _draft(name):
	doc = frappe.get_doc("Checklist Run", name)
	if doc.docstatus != 0:
		frappe.throw(_("This checklist is already signed."))
	return doc


def _row(doc, idx):
	row = next((r for r in doc.answers if r.idx == cint(idx)), None)
	if not row:
		frappe.throw(_("Question {0} not found").format(idx))
	return row


@frappe.whitelist(methods=["POST"])
def save_answer(name: str, idx: int, value: str | None = None, corrective_action: str | None = None,
                note: str | None = None) -> dict:
	"""Saves one answer as soon as it is tapped (a dropped connection loses one tap at most)."""
	_require(KIOSK_ROLES)
	doc = _draft(name)
	row = _row(doc, idx)
	if value is not None:
		row.value = str(value).strip()
	if corrective_action is not None:
		row.corrective_action = corrective_action.strip()
	if note is not None:
		row.note = note.strip()
	row.answered_at = now_datetime()
	if doc.status in (schedule.PENDING,):
		doc.status = schedule.IN_PROGRESS
	doc.save(ignore_permissions=True)
	row = _row(doc, idx)
	return {"result": row.result, "status": doc.status}


@frappe.whitelist(methods=["POST"])
def upload_photo(name: str, idx: int, data: str, filename: str = "photo.jpg") -> dict:
	"""data = base64 (a data: URL is fine). The tablet shrinks photos before sending them."""
	_require(KIOSK_ROLES)
	doc = _draft(name)
	row = _row(doc, idx)
	if "," in data[:100]:
		data = data.split(",", 1)[1]
	content = base64.b64decode(data)
	if len(content) > MAX_PHOTO_BYTES:
		frappe.throw(_("The photo is too large."))
	f = frappe.get_doc({"doctype": "File", "file_name": f"{doc.name}-{row.idx}-{filename}", "is_private": 1,
	                    "attached_to_doctype": "Checklist Run", "attached_to_name": doc.name, "content": content})
	f.save(ignore_permissions=True)
	row.photo = f.file_url
	row.answered_at = now_datetime()
	if doc.status == schedule.PENDING:
		doc.status = schedule.IN_PROGRESS
	doc.save(ignore_permissions=True)
	return {"photo": f.file_url, "result": _row(doc, idx).result}


@frappe.whitelist(methods=["POST"])
def sign_off(name: str, employee: str, pin: str) -> dict:
	"""Checks the PIN (same lock as clock-in) and signs: the run is submitted and locked."""
	_require(KIOSK_ROLES)
	doc = _draft(name)
	found = scoring.problems([r.as_dict() for r in doc.answers])
	if found:
		return {"ok": False, "problems": [problem_message(p) for p in found]}
	if not team_api.verify_pin(employee, pin):
		return {"ok": False, "wrong_pin": True}
	doc.employee = employee
	doc.employee_name = frappe.db.get_value("Employee", employee, "employee_name")
	doc.signed_at = now_datetime()
	doc.flags.ignore_permissions = True
	doc.submit()
	return {"ok": True, "status": doc.status, "issues": doc.issues, "late": doc.late, "signed_at": str(doc.signed_at)}


# ------------------------------------------------------------------ managers


@frappe.whitelist(methods=["POST"])
def review(names, note: str | None = None) -> int:
	"""Marks signed checklists as reviewed (one or many)."""
	_require(MANAGER_ROLES)
	if isinstance(names, str):
		names = json.loads(names) if names.startswith("[") else [names]
	n = 0
	for name in names:
		doc = frappe.get_doc("Checklist Run", name)
		if doc.docstatus == 1 and doc.status != schedule.REVIEWED:
			mark_reviewed(doc, note)
			n += 1
	return n


def waiting_lines() -> list[dict]:
	"""Lines for Today > Waiting on you (recipe_management/dashboard.py)."""
	if not frappe.has_permission("Checklist Run", "read"):
		return []
	out = []
	overdue = frappe.get_all("Checklist Run", filters={"docstatus": 0, "status": ("in", [schedule.OVERDUE, schedule.MISSED]),
	                                                   "run_date": (">=", add_days(nowdate(), -1))},
	                         fields=["name", "title", "area", "status", "window_end"], order_by="window_end asc", limit=5)
	for r in overdue:
		out.append({"label": _("Checklist overdue: {0}").format(r.title),
		            "detail": _("{0}, due {1}").format(r.area, str(r.window_end)[11:16]) +
		            (" · " + _("Missed") if r.status == schedule.MISSED else ""),
		            "route": "kitchen-checks", "tone": "danger"})
	if set(MANAGER_ROLES) & set(frappe.get_roles()):
		to_review = frappe.db.count("Checklist Run", {"docstatus": 1, "requires_review": 1,
		                                              "status": ("in", [schedule.COMPLETED, schedule.WITH_ISSUES])})
		issues = frappe.db.count("Checklist Run", {"docstatus": 1, "status": schedule.WITH_ISSUES})
		if to_review or issues:
			out.append({"label": _("Checklists to review"),
			            "detail": _("{0} to review, {1} with issues").format(to_review, issues),
			            "route": "List/Checklist Run?docstatus=1&status=[\"in\",[\"Completed\",\"Completed with issues\"]]", "tone": "warning"})
	return out


@frappe.whitelist()
def day_summary(date: str | None = None) -> dict:
	"""Done / overdue / issues per area for one day (manager card and workspace)."""
	_require(MANAGER_ROLES)
	day = getdate(date or nowdate())
	rows = frappe.get_all("Checklist Run", filters={"run_date": day, "docstatus": ("<", 2)}, fields=["area", "status"])
	by_area = {}
	for r in rows:
		by_area.setdefault(r.area, []).append(r.status)
	return {"date": str(day), "all": schedule.summary([r.status for r in rows]),
	        "areas": {a: schedule.summary(s) for a, s in sorted(by_area.items())}}
