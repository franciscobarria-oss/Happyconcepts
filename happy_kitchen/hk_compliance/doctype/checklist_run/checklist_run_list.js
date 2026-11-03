// Checklist Run list colours (hk_compliance/schedule.py statuses).
frappe.listview_settings["Checklist Run"] = {
	add_fields: ["status", "late"],
	get_indicator(doc) {
		const colour = { Pending: "gray", "In progress": "blue", Overdue: "orange", Missed: "red", Completed: "green",
			"Completed with issues": "red", Reviewed: "green" }[doc.status] || "gray";
		return [__(doc.status), colour, `status,=,${doc.status}`];
	},
};
