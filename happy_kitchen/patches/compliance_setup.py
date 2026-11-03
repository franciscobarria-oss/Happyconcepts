import frappe

from happy_kitchen.hk_compliance import setup_data as d


def execute():
	"""Kitchen Checks starting data: one area, three editable checklists with their schedules
	switched OFF (nothing is due until a manager ticks Active), corrective-action quick picks and
	settings defaults. Idempotent: records the team already has are left alone."""
	# Patches run before DocTypes are synced on migrate: the module must be known, or the DocType
	# path resolves to frappe.core, and each DocType must be loaded before records are inserted.
	if not frappe.db.exists("Module Def", "HK Compliance"):
		frappe.get_doc({"doctype": "Module Def", "module_name": "HK Compliance", "app_name": "happy_kitchen"}).insert(
			ignore_permissions=True)
	for doctype in ("check_area", "checklist_template_item", "checklist_template", "checklist_schedule",
	                "checklist_run_answer", "checklist_run", "corrective_action_preset", "compliance_settings"):
		frappe.reload_doc("hk_compliance", "doctype", doctype)

	if not frappe.db.exists("Role", "Compliance Manager"):
		frappe.get_doc({"doctype": "Role", "role_name": "Compliance Manager", "desk_access": 1}).insert(ignore_permissions=True)

	company = frappe.defaults.get_global_default("company")
	abbr = frappe.db.get_value("Company", company, "abbr") if company else None
	area, area_zh, dept = d.AREA
	department = f"{dept} - {abbr}" if abbr and frappe.db.exists("Department", f"{dept} - {abbr}") else None
	if not frappe.db.exists("Check Area", area):
		frappe.get_doc({"doctype": "Check Area", "area_name": area, "area_name_zh": area_zh,
		                "department": department}).insert(ignore_permissions=True)

	for t in d.TEMPLATES:
		if frappe.db.exists("Checklist Template", t["title"]):
			continue
		frappe.get_doc({"doctype": "Checklist Template", "title": t["title"], "title_zh": t["title_zh"],
		                "category": t["category"], "requires_review": t["requires_review"],
		                "items": [{"required": 1, **it} for it in t["items"]]}).insert(ignore_permissions=True)
		freq, start, due = t["schedule"]
		frappe.get_doc({"doctype": "Checklist Schedule", "template": t["title"], "area": area, "frequency": freq,
		                "start_time": start, "due_time": due, "grace_minutes": 15, "active": 0}).insert(ignore_permissions=True)

	for action, zh, category in d.PRESETS:
		if not frappe.db.exists("Corrective Action Preset", action):
			frappe.get_doc({"doctype": "Corrective Action Preset", "action": action, "action_zh": zh,
			                "category": category}).insert(ignore_permissions=True)

	s = frappe.get_single("Compliance Settings")
	if not s.missed_after_hours:
		s.enabled, s.missed_after_hours, s.notify_overdue = 1, 4, 1
		s.save(ignore_permissions=True)
