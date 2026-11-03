// Checklist Run form: answers are given and signed on the Kitchen Checks tablet screen (PIN);
// managers review signed runs here.
frappe.ui.form.on("Checklist Run", {
	refresh(frm) {
		if (frm.doc.docstatus === 0 && !frm.is_new()) {
			frm.add_custom_button(__("Open on the tablet screen"), () => frappe.set_route("kitchen-checks"));
			frm.set_intro(__("Answer and sign this checklist on the Kitchen Checks screen with your PIN."), "blue");
		}
		const manager = frappe.user.has_role("Compliance Manager") || frappe.user.has_role("System Manager");
		if (frm.doc.docstatus === 1 && frm.doc.status !== "Reviewed" && manager) {
			frm.add_custom_button(__("Mark as reviewed"), () => {
				frappe.prompt({ fieldname: "note", fieldtype: "Small Text", label: __("Review note") }, async (v) => {
					await frappe.xcall("happy_kitchen.hk_compliance.api.review", { names: [frm.doc.name], note: v.note || "" });
					frm.reload_doc();
				}, __("Mark as reviewed"), __("Reviewed"));
			}).addClass("btn-primary");
		}
		if (frm.doc.issues) {
			frm.dashboard.set_headline_alert(__("{0} failed answers: see what was done in the Answers table.", [frm.doc.issues]), "red");
		}
	},
});
