// Copyright (c) 2026, Happy Kitchen and contributors
// For license information, please see license.txt

frappe.query_reports["Ingredients and Packaging by Supplier"] = {
	filters: [
		{ fieldname: "supplier", label: __("Supplier"), fieldtype: "Link", options: "Supplier" },
		{
			fieldname: "component_type",
			label: __("Type"),
			fieldtype: "Select",
			options: "\nIngredient\nPackaging",
		},
		{ fieldname: "item", label: __("Item"), fieldtype: "Link", options: "Item" },
		{ fieldname: "recipe", label: __("Recipe"), fieldtype: "Link", options: "Recipe" },
		{
			fieldname: "price_list",
			label: __("Price List"),
			fieldtype: "Link",
			options: "Price List",
			get_query: () => ({ filters: { buying: 1 } }),
		},
		{ fieldname: "show_unpriced", label: __("Include items with no price"), fieldtype: "Check", default: 1 },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && column.fieldname === "diff_pct" && data.diff_pct > 0) value = `<span class="text-danger">${value}</span>`;
		if (data && data.no_price && column.fieldname === "item_name") value = `<span class="text-warning">${value}</span>`;
		return value;
	},
};
