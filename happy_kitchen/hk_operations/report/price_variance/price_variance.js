// Copyright (c) 2026, Happy Kitchen and contributors
// For license information, please see license.txt

frappe.query_reports["Price Variance"] = {
	filters: [
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", reqd: 1,
		  default: frappe.datetime.add_months(frappe.datetime.get_today(), -1) },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", reqd: 1, default: frappe.datetime.get_today() },
		{ fieldname: "supplier", label: __("Supplier"), fieldtype: "Link", options: "Supplier" },
		{ fieldname: "item_code", label: __("Item"), fieldtype: "Link", options: "Item" },
		{ fieldname: "only_changes", label: __("Only Price Changes"), fieldtype: "Check", default: 1 },
		{ fieldname: "tolerance", label: __("Ignore Changes Under %"), fieldtype: "Float", default: 0.5 },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && ["vs_po", "vs_list", "vs_last"].includes(column.fieldname) && data[column.fieldname] != null) {
			const v = data[column.fieldname];
			if (v > 0.5) value = `<span class="text-danger"><b>+${value}</b></span>`;
			else if (v < -0.5) value = `<span class="text-success">${value}</span>`;
		}
		return value;
	},
};
