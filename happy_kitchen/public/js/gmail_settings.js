// Gmail Settings: "Check connection" (read-only profile call) and "Pick up orders now".
frappe.ui.form.on("Gmail Settings", {
	refresh(frm) {
		if (!frm.doc.client_id) return;
		frm.add_custom_button(__("Check connection"), async () => {
			const email = await frappe.xcall("happy_kitchen.hk_operations.gmail_orders.test_connection");
			frappe.msgprint(__("Connected to {0}. Read-only access.", [frappe.utils.escape_html(email)]));
		});
		frm.add_custom_button(__("Pick up orders now"), async () => {
			const r = await frappe.xcall("happy_kitchen.hk_operations.gmail_orders.fetch_now");
			frappe.msgprint(__("{0} new emails: {1} draft orders, {2} to review, {3} ignored, {4} failed.", [r.new, r.draft, r.review, r.ignored, r.failed]));
			frm.reload_doc();
		});
	},
});
