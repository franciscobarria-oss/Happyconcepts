// Email Order: the email and its PDFs next to what the system read, plus ways to close a review.
const HK_EO = "happy_kitchen.hk_operations.gmail_orders.";

function hk_eo_esc(s) {
	return frappe.utils.escape_html(s == null ? "" : String(s));
}

function hk_eo_render(frm, d) {
	const files = d.files.map((f) => {
		const pdf = (f.file_name || "").toLowerCase().endsWith(".pdf");
		const link = `<a href="${hk_eo_esc(f.file_url)}" target="_blank">${hk_eo_esc(f.file_name)}</a>`;
		return pdf ? `<div style="margin-bottom:8px">${link}<iframe src="${hk_eo_esc(f.file_url)}" style="width:100%;height:480px;border:1px solid var(--border-color);margin-top:4px"></iframe></div>` : `<div>${link}</div>`;
	}).join("");
	const pre = (t) => `<pre style="white-space:pre-wrap;max-height:240px;overflow:auto;font-size:12px">${hk_eo_esc(t)}</pre>`;
	const left = `<h6>${__("What was sent")}</h6>${files || ""}
		<div class="text-muted small">${__("Email text")}</div>${pre(d.email_text || __("(empty)"))}
		${d.pdf_text ? `<div class="text-muted small">${__("What the reader got from the PDFs")}</div>${pre(d.pdf_text)}` : ""}`;
	const rows = d.lines.map((l) => `<tr${l.item ? "" : ' style="background:var(--yellow-highlight-color, #fff8e1)"'}>
		<td>${hk_eo_esc(l.po_no)}</td><td>${hk_eo_esc(l.delivery_date)}</td><td>${hk_eo_esc(l.external_sku)}</td>
		<td>${hk_eo_esc(l.description)}</td><td class="text-right">${hk_eo_esc(l.qty)}</td>
		<td>${hk_eo_esc(l.item)}</td><td>${hk_eo_esc(l.sales_order)}</td></tr>`).join("");
	const table = rows ? `<table class="table table-bordered table-sm"><thead><tr>
		<th>${__("PO")}</th><th>${__("Delivery")}</th><th>${__("Code")}</th><th>${__("Description")}</th>
		<th>${__("Qty")}</th><th>${__("Item")}</th><th>${__("Sales Order")}</th></tr></thead><tbody>${rows}</tbody></table>` : `<p class="text-muted">${__("No order lines were read.")}</p>`;
	const unread = d.unparsed.length ? `<div class="text-danger small">${__("Lines it could not read")}</div>${pre(d.unparsed.join("\n"))}` : "";
	const err = d.error ? `<div class="text-danger small">${__("Error")}</div>${pre(d.error)}` : "";
	const why = d.reasons.map((r) => `<li>${hk_eo_esc(r)}</li>`).join("");
	const right = `<h6>${__("What the system understood")}</h6><ul>${why}</ul>${table}${unread}${err}`;
	frm.get_field("review_html").$wrapper.html(
		`<div style="display:flex;gap:16px;flex-wrap:wrap"><div style="flex:1 1 360px;min-width:0">${left}</div><div style="flex:1 1 360px;min-width:0">${right}</div></div>`);
}

frappe.ui.form.on("Email Order", {
	async refresh(frm) {
		if (frm.is_new()) return;
		try {
			hk_eo_render(frm, await frappe.xcall(HK_EO + "review_data", { name: frm.doc.name }));
		} catch (e) {
			frm.get_field("review_html").$wrapper.html("");
		}
		if (!["Needs review", "Failed"].includes(frm.doc.status)) return;
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
	},
});
