// Copyright (c) 2026, Happy Kitchen and contributors
// For license information, please see license.txt

frappe.ui.form.on("Overtime Entry", {
	refresh(frm) {
		if (frm.doc.docstatus === 0 && !frm.is_new() && frappe.model.can_submit("Overtime Entry")) {
			frm.page.set_primary_action(__("Approve"), () => frm.savesubmit());
		}
		if (frm.doc.docstatus === 1) {
			frm.page.clear_primary_action();
		}
	},
	employee: preview,
	overtime_rate: preview,
	hours: preview,
});

async function preview(frm) {
	const d = frm.doc;
	if (d.docstatus !== 0 || !d.employee) return;
	if (!d.overtime_rate) {
		const def = (await frappe.db.get_value("Employee", d.employee, "hk_default_overtime_rate")).message;
		if (def && def.hk_default_overtime_rate) {
			await frm.set_value("overtime_rate", def.hk_default_overtime_rate);
			return; // set_value re-triggers preview
		}
		return;
	}
	const r = await frappe.call({
		method: "happy_kitchen.hk_operations.doctype.overtime_entry.overtime_entry.preview",
		args: { employee: d.employee, overtime_rate: d.overtime_rate, hours: d.hours || 0 },
	});
	if (r.message && "amount" in r.message) {
		frm.set_value("hourly_amount", r.message.hourly_amount);
		frm.set_value("amount", r.message.amount);
	}
}
