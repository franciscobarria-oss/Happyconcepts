frappe.ui.form.on("Purchase Receipt", {
	refresh(frm) {
		if (frm.doc.hk_has_discrepancy && frm.doc.hk_delivery_flags) {
			frm.dashboard.set_headline_alert(
				`<b>${__("Delivery differs from the order")}:</b><br>${frappe.utils.escape_html(frm.doc.hk_delivery_flags).replace(/\n/g, "<br>")}`,
				"orange"
			);
		}
	},
});
