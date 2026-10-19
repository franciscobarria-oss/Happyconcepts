// Product labels for a submitted order: a summary line, "Print labels" and the label queue.
frappe.ui.form.on("Sales Order", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;
		frappe.call("happy_kitchen.hk_operations.labels.sales_order_labels", { sales_order: frm.doc.name }).then(({ message: jobs }) => {
			jobs = jobs || [];
			frm.add_custom_button(__("Print labels"), () => hk_print_labels_dialog(frm, jobs), __("Labels"));
			frm.add_custom_button(__("Label queue"), () => frappe.set_route("List", "Label Job", { sales_order: frm.doc.name }), __("Labels"));
			if (!jobs.length) return;
			const count = (s) => jobs.filter((j) => j.status === s).reduce((n, j) => n + (j.label_count || 0), 0);
			const parts = [
				[count("Printed"), __("printed"), "green"],
				[count("Queued") + count("Printing"), __("waiting for the printer"), "blue"],
				[count("Needs check"), __("waiting for a label check"), "orange"],
				[count("Failed"), __("failed"), "red"],
			].filter(([n]) => n);
			if (parts.length)
				frm.dashboard.add_comment(
					`<b>${__("Labels")}:</b> ` + parts.map(([n, t, c]) => `<span class="indicator-pill ${c}">${n} ${t}</span>`).join(" "),
					"blue", true
				);
		});
	},
});

function hk_print_labels_dialog(frm, jobs) {
	const done = {};
	jobs.filter((j) => j.status === "Printed").forEach((j) => (done[j.so_detail] = (done[j.so_detail] || 0) + j.qty));
	const d = new frappe.ui.Dialog({
		title: __("Print labels for {0}", [frm.doc.name]),
		size: "large",
		fields: [
			{
				fieldtype: "HTML",
				options: `<p class="text-muted">${__("Pick the lines to print. Pieces = how many pieces the labels cover; the item's Pieces per label decides how many labels that is.")}</p>`,
			},
			{
				fieldname: "rows", fieldtype: "Table", cannot_add_rows: true, in_place_edit: true,
				data: frm.doc.items.map((it) => ({
					so_detail: it.name, item_code: it.item_code, item_name: it.item_name,
					qty: it.stock_qty || it.qty, printed: done[it.name] || 0, print: done[it.name] ? 0 : 1,
				})),
				fields: [
					{ fieldname: "print", fieldtype: "Check", label: __("Print"), in_list_view: 1, columns: 1 },
					{ fieldname: "item_name", fieldtype: "Data", label: __("Product"), in_list_view: 1, read_only: 1, columns: 5 },
					{ fieldname: "qty", fieldtype: "Float", label: __("Pieces"), in_list_view: 1, columns: 2 },
					{ fieldname: "printed", fieldtype: "Float", label: __("Already printed"), in_list_view: 1, read_only: 1, columns: 2 },
					{ fieldname: "so_detail", fieldtype: "Data", hidden: 1 },
					{ fieldname: "item_code", fieldtype: "Data", hidden: 1 },
				],
			},
		],
		primary_action_label: __("Send to printer"),
		primary_action(v) {
			const rows = (v.rows || []).filter((r) => r.print && r.qty > 0).map((r) => ({ so_detail: r.so_detail, qty: r.qty }));
			if (!rows.length) return frappe.msgprint(__("Tick at least one line."));
			frappe.call({
				method: "happy_kitchen.hk_operations.labels.queue_sales_order",
				args: { sales_order: frm.doc.name, rows },
				freeze: true,
			}).then(({ message }) => {
				d.hide();
				frappe.show_alert({ message: __("{0} label job(s) added.", [(message || []).length]), indicator: "green" });
				frm.reload_doc();
			});
		},
	});
	d.show();
}
