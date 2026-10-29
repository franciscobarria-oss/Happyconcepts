frappe.listview_settings["OEM Spec Sheet"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		return {
			Draft: [__("Draft"), "orange", "status,=,Draft"],
			Approved: [__("Approved"), "green", "status,=,Approved"],
			Superseded: [__("Superseded"), "gray", "status,=,Superseded"],
		}[doc.status];
	},
};
