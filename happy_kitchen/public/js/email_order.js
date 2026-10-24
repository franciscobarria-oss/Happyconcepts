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
	const canEdit = frappe.user.has_role("Sales Manager") || frappe.user.has_role("System Manager");
	const rows = d.lines.map((l) => {
		const state = !l.item ? __("No product") : l.item_confirmed ? __("Item confirmed") : l.item_created ? __("New product made") : __("Matched by the reader");
		const btns = canEdit && l.item ? `<button class="btn btn-xs btn-default hk-eo-ok" data-idx="${l.idx}"${l.item_confirmed ? " disabled" : ""}>${__("Confirm item")}</button>
			<button class="btn btn-xs btn-default hk-eo-change" data-idx="${l.idx}">${__("Change item")}</button>` : "";
		return `<tr${l.item && l.item_confirmed ? "" : ' style="background:var(--yellow-highlight-color, #fff8e1)"'}>
		<td>${hk_eo_esc(l.po_no)}</td><td>${hk_eo_esc(l.delivery_date)}</td><td>${hk_eo_esc(l.external_sku)}</td>
		<td>${hk_eo_esc(l.description)}</td><td class="text-right">${hk_eo_esc(l.qty)}</td>
		<td>${hk_eo_esc(l.item)} ${hk_eo_esc(l.item_name)}<div class="text-muted small">${state}</div></td>
		<td>${hk_eo_esc(l.sales_order)}</td><td style="white-space:nowrap">${btns}</td></tr>`;
	}).join("");
	const table = rows ? `<table class="table table-bordered table-sm"><thead><tr>
		<th>${__("PO")}</th><th>${__("Delivery")}</th><th>${__("Code")}</th><th>${__("Description")}</th>
		<th>${__("Qty")}</th><th>${__("Suggested item")}</th><th>${__("Sales Order")}</th><th></th></tr></thead><tbody>${rows}</tbody></table>` : `<p class="text-muted">${__("No order lines were read.")}</p>`;
	const unread = d.unparsed.length ? `<div class="text-danger small">${__("Lines it could not read")}</div>${pre(d.unparsed.join("\n"))}` : "";
	const err = d.error ? `<div class="text-danger small">${__("Error")}</div>${pre(d.error)}` : "";
	const why = d.reasons.map((r) => `<li>${hk_eo_esc(r)}</li>`).join("");
	const right = `<h6>${__("What the system understood")}</h6><ul>${why}</ul>${table}${unread}${err}`;
	frm.get_field("review_html").$wrapper.html(
		`<div style="display:flex;gap:16px;flex-wrap:wrap"><div style="flex:1 1 360px;min-width:0">${left}</div><div style="flex:1 1 360px;min-width:0">${right}</div></div>`);
	const w = frm.get_field("review_html").$wrapper;
	const call = async (idx, item) => {
		await frappe.xcall(HK_EO + "confirm_line_item", { name: frm.doc.name, idx, item: item || null });
		frm.reload_doc();
	};
	w.find(".hk-eo-ok").on("click", (e) => call($(e.currentTarget).data("idx")));
	w.find(".hk-eo-change").on("click", (e) => {
		const idx = $(e.currentTarget).data("idx");
		frappe.prompt([{ fieldname: "item", fieldtype: "Link", options: "Item", label: __("Item"), reqd: 1 }],
			(v) => call(idx, v.item), __("Change item"), __("Change item"));
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
		const confirmOrder = () => frm.add_custom_button(__("Order confirmed"), () => {
			frappe.confirm(__("The order matches the PDF? Mark it as confirmed."), async () => {
				await frappe.xcall(HK_EO + "confirm_order", { name: frm.doc.name });
				frm.reload_doc();
			});
		});
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
