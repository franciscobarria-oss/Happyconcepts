// Copyright (c) 2026, Happy Kitchen and contributors
// For license information, please see license.txt

frappe.query_reports["Recipe Ingredient Usage"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
		},
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{
			fieldname: "source",
			label: __("Based On"),
			fieldtype: "Select",
			options: "Production Log\nProduction Plan",
			default: "Production Log",
		},
		{ fieldname: "warehouse", label: __("Warehouse"), fieldtype: "Link", options: "Warehouse" },
		{ fieldname: "recipe", label: __("Recipe"), fieldtype: "Link", options: "Recipe" },
		{
			fieldname: "planned_batches",
			label: __("Planned Batches"),
			fieldtype: "Float",
			description: __("With a recipe: show usage for this many batches instead of the date range."),
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && column.fieldname === "shortage_qty" && data.shortage_qty > 0)
			value = `<span class="text-danger"><b>${value}</b></span>`;
		return value;
	},
};
