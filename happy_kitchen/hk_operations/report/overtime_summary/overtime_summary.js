// Copyright (c) 2026, Happy Kitchen and contributors
// For license information, please see license.txt

frappe.query_reports["Overtime Summary"] = {
	filters: [
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", reqd: 1,
		  default: frappe.datetime.month_start(frappe.datetime.add_months(frappe.datetime.get_today(), -1)) },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", reqd: 1, default: frappe.datetime.month_end() },
		{ fieldname: "employee", label: __("Employee"), fieldtype: "Link", options: "Employee" },
		{ fieldname: "department", label: __("Department"), fieldtype: "Link", options: "Department" },
	],
};
