frappe.listview_settings["Stock Take"] = {
	add_fields: ["status", "counted_rows", "total_rows", "rejection_comment"],
	get_indicator(doc) {
		if (doc.status === "Approved") return [__("Approved"), "green", "status,=,Approved"];
		if (doc.status === "Submitted") return [__("Waiting for Approval"), "orange", "status,=,Submitted"];
		if (doc.rejection_comment) return [__("Rejected - Draft"), "red", "status,=,Draft"];
		return [__("Draft"), "gray", "status,=,Draft"];
	},
};
