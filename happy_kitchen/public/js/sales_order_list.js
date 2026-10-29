// Sales Order list and form badge: Draft / Confirmed / Completed (hk_operations/order_stage.py).
// Appended after ERPNext's sales_order_list.js; its own indicator stays for any other case.
(function () {
	const settings = (frappe.listview_settings["Sales Order"] = frappe.listview_settings["Sales Order"] || {});
	const erpnext_indicator = settings.get_indicator;
	["per_delivered", "per_billed", "delivery_date", "status"].forEach((f) => {
		settings.add_fields = settings.add_fields || [];
		if (!settings.add_fields.includes(f)) settings.add_fields.push(f);
	});
	settings.get_indicator = function (doc) {
		if (doc.docstatus === 1) {
			const delivered = flt(doc.per_delivered);
			if (delivered >= 100 || doc.status === "Completed" || doc.status === "Closed")
				return [__("Completed"), "green", "status,=,Completed"];
			if (doc.status !== "On Hold") {
				const late = !!doc.delivery_date && doc.delivery_date < frappe.datetime.get_today();
				return late
					? [__("Confirmed (late)"), "red", "docstatus,=,1|per_delivered,<,100|delivery_date,<," + frappe.datetime.get_today()]
					: [__("Confirmed"), "blue", "docstatus,=,1|per_delivered,<,100"];
			}
		}
		return erpnext_indicator ? erpnext_indicator(doc) : undefined;
	};
})();
