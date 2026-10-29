// Copyright (c) 2026, Happy Kitchen and contributors
// For license information, please see license.txt

frappe.query_reports["Recipe Cost Analysis"] = {
	filters: [
		{
			fieldname: "recipe_type",
			label: __("Recipe Type"),
			fieldtype: "Select",
			options: "\nFinished Product\nBatch Preparation\nRecipe Component",
		},
		{ fieldname: "recipe", label: __("Recipe"), fieldtype: "Link", options: "Recipe" },
		{ fieldname: "status", label: __("Status"), fieldtype: "Select", options: "\nDraft\nActive\nArchived" },
	],
	tree: true,
	initial_depth: 1,
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && data.indent === 0) value = `<b>${value}</b>`;
		return value;
	},
};
