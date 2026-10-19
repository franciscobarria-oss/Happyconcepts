frappe.ui.form.on("Label Printer", {
	refresh(frm) {
		const $w = frm.fields_dict.status_html.$wrapper;
		if (frm.is_new()) return $w.empty();
		frm.add_custom_button(__("Print test label"), () =>
			frappe.call("happy_kitchen.hk_operations.labels.print_test_label", { printer: frm.doc.name }).then(({ message }) =>
				frappe.show_alert({ message: __("Test label {0} sent. It prints within a few seconds if the Pi is online.", [message]), indicator: "green" })
			)
		);
		frm.add_custom_button(__("Label queue"), () => frappe.set_route("List", "Label Job"));
		frappe.call("happy_kitchen.hk_operations.labels.printer_status", { printer: frm.doc.name }).then(({ message: s }) => {
			if (!s) return;
			const pill = s.online
				? `<span class="indicator-pill green">${__("Online")}</span>`
				: `<span class="indicator-pill red">${__("Offline")}</span>`;
			const seen = s.last_seen ? __("Last heard from {0}", [frappe.datetime.comment_when(s.last_seen)]) : __("The Raspberry Pi has never connected.");
			const problem = s.online && s.agent_problem ? `<p class="text-danger">${frappe.utils.escape_html(s.agent_problem)}</p>` : "";
			$w.html(`<p>${pill} <span class="text-muted">${seen}</span></p>${problem}
				<p class="text-muted small">${__("{0} label job(s) waiting for a printer.", [s.queued])}</p>`);
		});
	},
});
