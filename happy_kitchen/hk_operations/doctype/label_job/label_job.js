frappe.ui.form.on("Label Job", {
	refresh(frm) {
		frm.disable_save();
		if (frm.is_new()) return;
		if (["Printed", "Failed", "Cancelled"].includes(frm.doc.status))
			frm.add_custom_button(__("Print again"), () =>
				frappe.call("happy_kitchen.hk_operations.labels.reprint", { job: frm.doc.name }).then(() => frm.reload_doc())
			);
		if (frm.doc.status === "Needs check" && frm.doc.item)
			frm.add_custom_button(__("Check the label"), () => frappe.set_route("Form", "Item", frm.doc.item));
		if (["Queued", "Needs check", "Failed"].includes(frm.doc.status))
			frm.add_custom_button(__("Cancel"), () =>
				frappe.db.set_value("Label Job", frm.doc.name, "status", "Cancelled").then(() => frm.reload_doc())
			);
		const $w = frm.fields_dict.preview_html.$wrapper;
		$w.html(`<p class="text-muted">${__("Drawing the label...")}</p>`);
		frappe.call("happy_kitchen.hk_operations.labels.job_preview", { job: frm.doc.name }).then(({ message: m }) => {
			if (!m) return;
			$w.html(`<img src="data:image/png;base64,${m.png}" alt="" style="width:440px; max-width:100%; border:1px solid var(--border-color); border-radius:6px; background:#fff">
				<p class="text-muted small" style="margin-top:6px">${__("{0} label(s). The first one is shown.", [m.labels])}</p>`);
		});
	},
});
