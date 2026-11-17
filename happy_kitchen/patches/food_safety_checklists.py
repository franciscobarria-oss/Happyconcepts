import frappe

from happy_kitchen.hk_compliance import schedule, setup_data as d


def execute():
	"""Food safety checklists (FS-D / FS-W / FS-M) with their schedules switched OFF: nothing comes
	due until a manager ticks Active. Idempotent: a checklist the team already has is left alone."""
	area = d.AREA[0]
	if not frappe.db.exists("Check Area", area):
		return  # compliance_setup makes the area; nothing to attach the schedules to without it
	if frappe.get_all("Checklist Template", filters={"title": ("like", "FS %")}, limit=1):
		return  # food safety checklists were already set up on this site (hcl-erp, by hand 2026-11-17)
	for t in d.FOOD_SAFETY:
		if frappe.db.exists("Checklist Template", t["title"]):
			continue
		frappe.get_doc({"doctype": "Checklist Template", "title": t["title"], "title_zh": t["title_zh"],
		                "category": t["category"], "requires_review": t["requires_review"],
		                "items": [{"required": 1, **it} for it in t["items"]]}).insert(ignore_permissions=True)
		s = t["schedule"]
		days = {day.lower(): int(day in s.get("weekdays", ())) for day in schedule.WEEKDAYS}
		frappe.get_doc({"doctype": "Checklist Schedule", "template": t["title"], "area": area,
		                "frequency": s["frequency"], "day_of_month": s.get("day_of_month"),
		                "start_time": s["start_time"], "due_time": s["due_time"], "grace_minutes": 15,
		                "active": 0, **days}).insert(ignore_permissions=True)
