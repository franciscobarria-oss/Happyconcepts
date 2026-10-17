// Copyright (c) 2026, Happy Kitchen and contributors
// For license information, please see license.txt

frappe.query_reports["Ingredient Cost Analysis"] = {
	filters: [
		{
			fieldname: "based_on",
			label: __("Based On"),
			fieldtype: "Select",
			options: "Recipes (1 batch each)\nProduction Log\nProduction Plan",
			default: "Recipes (1 batch each)",
			on_change() {
				const by_period = frappe.query_report.get_filter_value("based_on") !== "Recipes (1 batch each)";
				["from_date", "to_date", "warehouse"].forEach((f) => frappe.query_report.toggle_filter_display(f, !by_period));
				frappe.query_report.refresh();
			},
		},
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.month_start(), hidden: 1 },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today(), hidden: 1 },
		{ fieldname: "warehouse", label: __("Warehouse"), fieldtype: "Link", options: "Warehouse", hidden: 1 },
		{
			fieldname: "recipe_type",
			label: __("Recipe Type"),
			fieldtype: "Select",
			options: "\nFinished Product\nBatch Preparation\nRecipe Component",
		},
		{ fieldname: "recipe", label: __("Recipe"), fieldtype: "Link", options: "Recipe" },
		{
			fieldname: "component_type",
			label: __("Type"),
			fieldtype: "Select",
			options: "\nIngredient\nPackaging\nBatch Preparation\nRecipe Component",
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && data.bold) value = `<b>${value}</b>`;
		return value;
	},
};
