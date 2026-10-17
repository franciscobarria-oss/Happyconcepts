// Purchase Order MOQ hints. The server enforces the same rules (hk_operations/purchasing.py):
// quantities must be whole multiples of Item "Order in Multiples Of" (blocks save), and the order
// must reach Supplier "Minimum Order Amount" before submit. Here we only warn early on save.
frappe.ui.form.on("Purchase Order", {
	async after_save(frm) {
		if (frm.doc.docstatus !== 0 || !frm.doc.supplier) return;
		const r = await frappe.db.get_value("Supplier", frm.doc.supplier, "hk_min_order_amount");
		const min = flt(r.message && r.message.hk_min_order_amount);
		const total = flt(frm.doc.base_net_total);
		if (!min || total >= min) return;
		const cur = frappe.defaults.get_default("currency");
		frappe.show_alert({
			message: __("Below {0}'s minimum order of {1} ({2} more needed). You can keep the draft, but it can't be submitted yet.",
				[frm.doc.supplier, format_currency(min, cur), format_currency(min - total, cur)]),
			indicator: "orange",
		}, 10);
	},
});
