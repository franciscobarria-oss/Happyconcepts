frappe.ui.form.on("Opened Item", {
	refresh(frm) {
		if (!frm.is_new() && frm.doc.status === "Open") {
			frm.add_custom_button(__("Print label again"), () =>
				frappe
					.xcall("happy_kitchen.hk_operations.dates_api.print_opened_label", { name: frm.doc.name, labels: 1 })
					.then(() => frappe.show_alert({ message: __("Label sent to the printer"), indicator: "green" }))
			);
		}
	},
});
