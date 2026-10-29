frappe.query_reports["Ingredient Label Check"] = {
	filters: [
		{ fieldname: "only_open", label: __("Only ingredients with something to do"), fieldtype: "Check", default: 1 },
	],
};
