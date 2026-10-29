// Product labels for a submitted order: a summary line, "Print labels" and the label queue.
frappe.ui.form.on("Sales Order", {
	refresh(frm) {
		hk_order_stage(frm);
		hk_revision_buttons(frm);
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

// Revised orders: flag, "Mark revision as checked" (managers) and the history of changes.
function hk_revision_buttons(frm) {
	if (frm.is_new() || !(frm.doc.hk_revision_count || frm.doc.hk_needs_review)) return;
	frm.add_custom_button(__("Revision history"), () => frappe.set_route("List", "Order Revision", { sales_order: frm.doc.name }), __("Revision"));
	if (!frm.doc.hk_needs_review) return;
	frm.dashboard.add_comment(
		__("This order was changed after it came in. Check the changes before delivering."), "orange", true
	);
	if (frappe.user.has_role("Sales Manager") || frappe.user.has_role("System Manager"))
		frm.add_custom_button(__("Mark revision as checked"), async () => {
			await frappe.xcall("happy_kitchen.hk_operations.revisions_api.mark_checked", { sales_order: frm.doc.name });
			frm.reload_doc();
		}, __("Revision")).addClass("btn-primary");
}

// Draft -> Confirmed -> Completed: a step bar on top and one button for the next step.
// Same rules as hk_operations/order_stage.py (built on docstatus / status / per_delivered only).
function hk_so_stage(doc) {
	const delivered = flt(doc.per_delivered);
	if (doc.docstatus === 0) return { stage: "Draft", color: "gray", next: "confirm" };
	if (doc.docstatus === 2) return { stage: "Cancelled", color: "red" };
	if (delivered >= 100 || doc.status === "Completed")
		return { stage: "Completed", color: "green", invoiced: flt(doc.per_billed) >= 100 };
	if (doc.status === "On Hold" || doc.status === "Closed")
		return { stage: doc.status, color: doc.status === "On Hold" ? "orange" : "gray" };
	const late = !!doc.delivery_date && doc.delivery_date < frappe.datetime.get_today();
	return { stage: "Confirmed", color: late ? "red" : "blue", late, part: delivered > 0, next: "deliver" };
}

function hk_order_stage(frm) {
	if (frm.is_new()) return;
	const s = hk_so_stage(frm.doc);
	const steps = ["Draft", "Confirmed", "Completed"];
	const at = steps.indexOf(s.stage);
	const bar = steps.map((name, i) => {
		const done = at >= 0 && i <= at;
		const now = i === at;
		return `<span style="display:inline-flex;align-items:center;gap:6px;${now ? "font-weight:600;" : done ? "" : "opacity:.45;"}">
			<span class="indicator-pill ${now ? s.color : done ? "green" : "gray"}" style="padding:2px 10px">${i + 1}. ${__(name)}</span></span>`;
	}).join(`<span style="opacity:.4;margin:0 6px">&rarr;</span>`);
	const notes = [];
	if (at < 0) notes.push(`<b>${__(s.stage)}</b>`);
	if (s.late) notes.push(`<span class="text-danger">${__("Late: the delivery date has passed.")}</span>`);
	if (s.part) notes.push(__("{0}% delivered so far.", [Math.round(flt(frm.doc.per_delivered))]));
	if (s.stage === "Completed" && !s.invoiced) notes.push(__("Delivered, not invoiced yet."));
	frm.dashboard.add_comment(`<b>${__("Order")}:</b> ${bar}${notes.length ? " &nbsp; " + notes.join(" ") : ""}`, "blue", true);

	// The one main button in the top bar: Confirm on a draft, Complete on a confirmed order.
	if (frm.is_dirty()) return;
	if (s.next === "confirm" && frm.has_perm("submit"))
		frm.page.set_primary_action(__("Confirm"), () => frm.savesubmit(), "check");
	if (s.next === "deliver" && frappe.model.can_create("Delivery Note"))
		frm.page.set_primary_action(__("Complete"), () => hk_mark_delivered(frm), "check");
}

function hk_mark_delivered(frm) {
	if (frm.doc.hk_needs_review)
		return frappe.msgprint(__("This order was revised. Mark the revision as checked before delivering."));
	frappe.confirm(
		__("Complete {0}? This makes and submits a Delivery Note for everything not yet delivered.", [frm.doc.name]),
		() => frappe.call({
			method: "happy_kitchen.hk_operations.order_stage_api.mark_delivered",
			args: { sales_order: frm.doc.name },
			freeze: true,
			freeze_message: __("Making the delivery note..."),
		}).then(({ message }) => {
			frappe.show_alert({ message: __("Completed: delivered with {0}", [message]), indicator: "green" });
			frm.reload_doc();
		})
	);
}
