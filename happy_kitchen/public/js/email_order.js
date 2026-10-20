// Email Order: read the email (and its PDFs) again after the reading rules changed.
frappe.ui.form.on("Email Order", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.sales_order || !["Needs review", "Failed"].includes(frm.doc.status)) return;
		frm.add_custom_button(__("Read again"), async () => {
			const status = await frappe.xcall("happy_kitchen.hk_operations.gmail_orders.reprocess", { name: frm.doc.name });
			frappe.show_alert({ message: __("Status: {0}", [__(status)]), indicator: "green" });
			frm.reload_doc();
		});
	},
});
