// Copyright (c) 2026, Happy Kitchen and contributors
// For license information, please see license.txt

frappe.query_reports["Inventory Variance"] = {
	filters: [
		{
			fieldname: "opening_stock_take",
			label: __("Opening Count"),
			fieldtype: "Link",
			options: "Stock Take",
			reqd: 1,
			get_query: () => ({ filters: { docstatus: 1 } }),
		},
		{
			fieldname: "closing_stock_take",
			label: __("Closing Count"),
			fieldtype: "Link",
			options: "Stock Take",
			reqd: 1,
			get_query: () => ({ filters: { docstatus: 1 } }),
		},
		{ fieldname: "only_out_of_tolerance", label: __("Only Out of Tolerance"), fieldtype: "Check" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && data.within_tolerance === false && ["variance_qty", "variance_cost", "variance_pct", "status", "item_name", "unexplained_cost"].includes(column.fieldname))
			value = `<span class="text-danger"><b>${value}</b></span>`;
		if (data && column.fieldname === "variance_pct" && data.variance_pct === null)
			value = `<span class="text-danger"><b>${__("n/a")}</b></span>`;
		return value;
	},
	onload(report) {
		// default to the two most recent approved counts
		frappe.db
			.get_list("Stock Take", { filters: { docstatus: 1 }, fields: ["name"], order_by: "posting_date desc, posting_time desc", limit: 2 })
			.then((rows) => {
				if (rows.length === 2 && !report.get_filter_value("closing_stock_take")) {
					report.set_filter_value({ opening_stock_take: rows[1].name, closing_stock_take: rows[0].name });
				}
			});
	},
};
