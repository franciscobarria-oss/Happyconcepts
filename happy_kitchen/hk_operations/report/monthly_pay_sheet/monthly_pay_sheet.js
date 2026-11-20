frappe.query_reports["Monthly Pay Sheet"] = {
	filters: [{ fieldname: "month", label: __("Month (YYYY-MM)"), fieldtype: "Data", reqd: 1,
		default: frappe.datetime.add_months(frappe.datetime.get_today(), -1).slice(0, 7) }],
	onload(report) {
		report.page.add_inner_button(__("Payment slip"), () => {
			const m = report.get_filter_value("month");
			const emp = (report.data.find(r => r.employee) || {}).employee;
			frappe.prompt({ fieldname: "employee", label: __("Employee"), fieldtype: "Link", options: "Employee",
				reqd: 1, default: emp }, v => window.open(
				`/api/method/happy_kitchen.hk_operations.pay_sheet_api.slip?employee=${encodeURIComponent(v.employee)}&month=${m}`),
				__("Payment slip"));
		});
	},
};
