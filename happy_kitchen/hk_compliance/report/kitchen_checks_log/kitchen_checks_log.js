// Kitchen Checks Log: every checklist run in a date range (hk_compliance).
frappe.query_reports["Kitchen Checks Log"] = {
	filters: [
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", default: frappe.datetime.add_days(frappe.datetime.get_today(), -6), reqd: 1 },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "area", label: __("Area"), fieldtype: "Link", options: "Check Area" },
		{ fieldname: "template", label: __("Checklist"), fieldtype: "Link", options: "Checklist Template" },
		{ fieldname: "only_problems", label: __("Only problems (missed, late, failed)"), fieldtype: "Check" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "status" && data && ["Missed", "Overdue", "Completed with issues"].includes(data.status)) {
			value = `<span style="color: var(--red-600); font-weight: 600">${value}</span>`;
		}
		return value;
	},
};
