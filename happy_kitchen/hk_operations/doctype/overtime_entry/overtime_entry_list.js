frappe.listview_settings["Overtime Entry"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		return {
			Draft: [__("To approve"), "orange", "status,=,Draft"],
			Approved: [__("Approved"), "green", "status,=,Approved"],
			Rejected: [__("Rejected"), "red", "status,=,Rejected"],
		}[doc.status];
	},
};
