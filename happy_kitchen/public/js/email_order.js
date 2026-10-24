// Email Order: the email and its PDFs next to what the system read, plus ways to close a review.
const HK_EO = "happy_kitchen.hk_operations.gmail_orders.";

function hk_eo_esc(s) {
	return frappe.utils.escape_html(s == null ? "" : String(s));
}

function hk_eo_render(frm, d) {
	frm._hk_review = d;
	const pre = (t) => `<pre style="white-space:pre-wrap;max-height:240px;overflow:auto;font-size:12px">${hk_eo_esc(t)}</pre>`;
	const files = d.files.map((f) => {
		const pdf = (f.file_name || "").toLowerCase().endsWith(".pdf");
		const link = `<a href="${hk_eo_esc(f.file_url)}" target="_blank">${hk_eo_esc(f.file_name)}</a>`;
		return pdf ? `<div style="margin-bottom:8px">${link}<iframe src="${hk_eo_esc(f.file_url)}" style="width:100%;height:70vh;border:1px solid var(--border-color);margin-top:4px"></iframe></div>` : `<div>${link}</div>`;
	}).join("");
	const left = `<h6>${__("What was sent")}</h6>${files || ""}
		<details${files ? "" : " open"}><summary class="text-muted small">${__("Email text")}</summary>${pre(d.email_text || __("(empty)"))}</details>
		${d.pdf_text ? `<details><summary class="text-muted small">${__("What the reader got from the PDFs")}</summary>${pre(d.pdf_text)}</details>` : ""}`;

	const canEdit = frappe.user.has_role("Sales Manager") || frappe.user.has_role("System Manager");
	const groups = [];
	d.lines.forEach((l) => {
		let g = groups.find((x) => x.po === (l.po_no || ""));
		if (!g) groups.push((g = { po: l.po_no || "", lines: [] }));
		g.lines.push(l);
	});
	const total = d.lines.filter((l) => l.item).length;
	const done = d.lines.filter((l) => l.item && l.item_confirmed).length;
	const pages = groups.map((g) => {
		const open = g.lines.filter((l) => l.item && !l.item_confirmed).length;
		const sos = [...new Set(g.lines.map((l) => l.sales_order).filter(Boolean))].join(", ");
		const dates = [...new Set(g.lines.map((l) => l.delivery_date).filter(Boolean))].join(", ");
		const rows = g.lines.map((l) => {
			const state = !l.item ? __("No product") : l.item_confirmed ? __("Item confirmed") : l.item_created ? __("New product made") : __("Matched by the reader");
			const change = canEdit && l.item ? `<button class="btn btn-xs btn-default hk-eo-change" data-idx="${l.idx}">${__("Change item")}</button>` : "";
			return `<tr${l.item && l.item_confirmed ? "" : ' style="background:var(--yellow-highlight-color, #fff8e1)"'}>
				<td>${hk_eo_esc(l.external_sku)}<div class="small">${hk_eo_esc(l.description)}</div></td>
				<td class="text-right">${hk_eo_esc(l.qty)}</td>
				<td>${hk_eo_esc(l.item)} ${hk_eo_esc(l.item_name)}<div class="text-muted small">${state}</div></td>
				<td style="white-space:nowrap">${change}</td></tr>`;
		}).join("");
		const title = g.po ? __("PO {0}", [g.po]) : __("Lines without a PO number");
		const btn = canEdit && open ? `<button class="btn btn-xs btn-primary hk-eo-po" data-po="${hk_eo_esc(g.po)}">${__("Confirm PO items")}</button>` : (open ? "" : `<span class="text-success">&#10003; ${__("PO confirmed")}</span>`);
		return `<div style="border:1px solid var(--border-color);border-radius:6px;margin-bottom:12px">
			<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 10px;background:var(--control-bg)">
				<div><b>${hk_eo_esc(title)}</b><span class="text-muted small"> ${dates ? hk_eo_esc(dates) : ""} ${sos ? "&middot; " + hk_eo_esc(sos) : ""}</span></div>${btn}</div>
			<table class="table table-sm" style="margin:0"><thead><tr><th>${__("Code")} / ${__("Description")}</th><th class="text-right">${__("Qty")}</th><th>${__("Suggested item")}</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>`;
	}).join("");
	const unread = d.unparsed.length ? `<div class="text-danger small">${__("Lines it could not read")}</div>${pre(d.unparsed.join("\n"))}` : "";
	const err = d.error ? `<div class="text-danger small">${__("Error")}</div>${pre(d.error)}` : "";
	const why = d.reasons.map((r) => `<li>${hk_eo_esc(r)}</li>`).join("");
	const progress = total ? `<div class="small" style="margin-bottom:8px"><b>${__("{0} of {1} lines confirmed", [done, total])}</b></div>` : "";
	const right = `<h6>${__("What the system understood")}</h6><ul>${why}</ul>${progress}
		${pages || `<p class="text-muted">${__("No order lines were read.")}</p>`}${unread}${err}`;
	frm.get_field("review_html").$wrapper.html(
		`<div style="display:flex;gap:16px;flex-wrap:wrap;align-items:flex-start"><div style="flex:1 1 420px;min-width:0;position:sticky;top:70px">${left}</div><div style="flex:1 1 420px;min-width:0">${right}</div></div>`);

	const w = frm.get_field("review_html").$wrapper;
	w.find(".hk-eo-po").on("click", async (e) => {
		await frappe.xcall(HK_EO + "confirm_po", { name: frm.doc.name, po_no: $(e.currentTarget).data("po") || "" });
		frm.reload_doc();
	});
	w.find(".hk-eo-change").on("click", (e) => {
		const idx = $(e.currentTarget).data("idx");
		frappe.prompt([{ fieldname: "item", fieldtype: "Link", options: "Item", label: __("Item"), reqd: 1 }],
			async (v) => {
				await frappe.xcall(HK_EO + "confirm_line_item", { name: frm.doc.name, idx, item: v.item });
				frm.reload_doc();
			}, __("Change item"), __("Change item"));
	});
}

frappe.ui.form.on("Email Order", {
	async refresh(frm) {
		if (frm.is_new()) return;
		try {
			hk_eo_render(frm, await frappe.xcall(HK_EO + "review_data", { name: frm.doc.name }));
		} catch (e) {
			frm.get_field("review_html").$wrapper.html(`<div class="text-danger">${__("The review could not be shown.")} ${hk_eo_esc(e && (e.message || e))}</div>`);
		}
		if (!["Needs review", "Failed", "Draft order", "Revised"].includes(frm.doc.status)) return;
		const confirmOrder = () => {
			frm.add_custom_button(__("Order confirmed"), () => {
				const d = frm._hk_review || { lines: [] };
				const open = d.lines.filter((l) => l.item && !l.item_confirmed).length;
				const msg = open
					? __("{0} lines are not confirmed yet. Confirm the whole order anyway? This confirms the items and submits the draft sales order.", [open])
					: __("The order matches the PDF? This confirms the items and submits the draft sales order.");
				frappe.confirm(msg, async () => {
					await frappe.xcall(HK_EO + "confirm_order", { name: frm.doc.name });
					frm.reload_doc();
				});
			}).addClass("btn-primary");
		};
		if (!["Needs review", "Failed"].includes(frm.doc.status)) return confirmOrder();
		if (!frm.doc.sales_order) {
			frm.add_custom_button(__("Read again"), async () => {
				const status = await frappe.xcall(HK_EO + "reprocess", { name: frm.doc.name });
				frappe.show_alert({ message: __("Status: {0}", [__(status)]), indicator: "green" });
				frm.reload_doc();
			});
		}
		frm.add_custom_button(__("Mark as entered by hand"), () => {
			frappe.prompt(
				[{ fieldname: "sales_order", fieldtype: "Link", options: "Sales Order", label: __("Sales Order you made (optional)") }],
				async (v) => {
					await frappe.xcall(HK_EO + "mark_done_by_hand", { name: frm.doc.name, sales_order: v.sales_order || null });
					frm.reload_doc();
				}, __("Entered by hand"), __("Done"));
		});
		frm.add_custom_button(__("Not an order"), () => {
			frappe.confirm(__("Close this email as not an order?"), async () => {
				await frappe.xcall(HK_EO + "mark_not_order", { name: frm.doc.name });
				frm.reload_doc();
			});
		});
		confirmOrder();
	},
});
