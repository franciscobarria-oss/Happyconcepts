// Copyright (c) 2026, Happy Kitchen and contributors
// For license information, please see license.txt

const HK_STK = "happy_kitchen.recipe_management.doctype.stock_take.stock_take.";

frappe.ui.form.on("Stock Take", {
	refresh(frm) {
		// counts go through Submit for Approval / Approve, not ERPNext's own Submit
		frm.set_intro("");
		frm.disable_save();
		frm.page.clear_primary_action();
		const status = frm.doc.status;
		const is_approver = frappe.user.has_role("Stock Take Approver");
		const own = frm.doc.submitted_by === frappe.session.user;

		if (frm.doc.rejection_comment && status === "Draft") {
			frm.dashboard.set_headline_alert(
				`${__("Rejected by {0}", [frm.doc.rejected_by])}: ${frappe.utils.escape_html(frm.doc.rejection_comment)}`,
				"red"
			);
		}
		if (frm.is_new()) {
			frm.enable_save();
			return;
		}
		frm.add_custom_button(__("Open Count Screen"), () => frappe.set_route("stock-take-count", frm.doc.name));
		frm.add_custom_button(__("Print Count Sheet"), () =>
			window.open(`/api/method/happy_kitchen.recipe_management.count_print.sheet?take=${encodeURIComponent(frm.doc.name)}`)
		);

		if (status === "Draft" && frm.doc.docstatus === 0) {
			frm.page.set_primary_action(__("Submit for Approval"), () =>
				frappe.confirm(__("Submit this count for approval? It can't be changed while it waits."), () =>
					frm.call({ method: HK_STK + "submit_for_approval", args: { name: frm.doc.name }, freeze: true }).then(() => frm.reload_doc())
				)
			);
		}
		if (status === "Submitted" && frm.doc.docstatus === 0 && is_approver) {
			if (own) {
				frm.dashboard.set_headline_alert(__("You submitted this count, so another approver has to approve or reject it."), "orange");
			} else {
				frm.page.set_primary_action(__("Approve"), () =>
					frappe.confirm(__("Approve this count? It will be locked and used as stock for the variance report."), () =>
						frm.call({ method: HK_STK + "approve", args: { name: frm.doc.name }, freeze: true }).then(() => frm.reload_doc())
					)
				);
				frm.add_custom_button(__("Reject"), () =>
					frappe.prompt(
						{ fieldname: "comment", fieldtype: "Small Text", label: __("Why is it rejected?"), reqd: 1 },
						(v) => frm.call({ method: HK_STK + "reject", args: { name: frm.doc.name, comment: v.comment }, freeze: true }).then(() => frm.reload_doc()),
						__("Reject Count"),
						__("Reject")
					)
				);
			}
		}
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("Inventory Variance"), () =>
				frappe.set_route("query-report", "Inventory Variance", { closing_stock_take: frm.doc.name })
			);
		}
	},
});
