frappe.listview_settings["Label Job"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const colour = { Queued: "blue", "Needs check": "orange", Printing: "blue", Printed: "green", Failed: "red", Cancelled: "gray" };
		return [__(doc.status), colour[doc.status] || "gray", "status,=," + doc.status];
	},
};
