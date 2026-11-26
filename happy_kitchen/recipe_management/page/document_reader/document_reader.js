// Copyright (c) 2026, Happy Kitchen and contributors
// Document reader: upload a PDF or picture, Gemini reads it like OCR, show the text and tables (copy / CSV / Excel).
(() => {
const API = "happy_kitchen.recipe_management.document_reader.";
const esc = (s) => frappe.utils.escape_html(s == null ? "" : String(s));

function css() {
	if (document.getElementById("hkdr-css")) return;
	$(`<style id="hkdr-css">
	.hkdr { max-width: 980px; margin: 0 auto; padding-bottom: 80px; }
	.hkdr-card { border: 1px solid var(--border-color); border-radius: 14px; padding: 14px; background: var(--card-bg); margin-bottom: 12px; }
	.hkdr-in { font-size: 14px; padding: 8px 12px; border-radius: 10px; border: 1px solid var(--border-color); background: var(--control-bg); width: 100%; }
	.hkdr-big { min-height: 46px; font-size: 16px; border-radius: 12px; margin: 8px 8px 0 0; }
	.hkdr-flag { background: var(--hk-warning-soft, #feebc8); border-radius: 8px; padding: 2px 8px; font-size: 12px; }
	.hkdr-wrap { overflow-x: auto; margin-top: 8px; }
	.hkdr table { border-collapse: collapse; font-size: 13px; }
	.hkdr td, .hkdr th { border: 1px solid var(--border-color); padding: 4px 8px; vertical-align: top; }
	.hkdr th { background: var(--control-bg); }
	</style>`).appendTo("head");
}

frappe.pages["document-reader"].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({ parent: wrapper, title: __("Document reader"), single_column: true });
	css();
	wrapper.hkdr = new DocReader(wrapper);
};
frappe.pages["document-reader"].on_page_show = (wrapper) => wrapper.hkdr.start();

function save(name, blob) {
	const a = document.createElement("a");
	a.href = URL.createObjectURL(blob); a.download = name; a.click();
	setTimeout(() => URL.revokeObjectURL(a.href), 5000);
}
const grid = (t) => (t.headers && t.headers.length ? [t.headers] : []).concat(t.rows);
const csv = (t) => grid(t).map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(",")).join("\r\n");
const tsv = (t) => grid(t).map((r) => r.map((c) => String(c).replace(/[\t\r\n]+/g, " ")).join("\t")).join("\n");

async function copy(text) {
	try { await navigator.clipboard.writeText(text); } catch (e) {
		const ta = document.createElement("textarea"); ta.value = text; document.body.appendChild(ta); ta.select(); document.execCommand("copy"); ta.remove();
	}
	frappe.show_alert({ message: __("Copied"), indicator: "green" }, 3);
}

function statusMap() { return { Queued: __("Waiting"), Reading: __("Reading"), Done: __("Ready"), Failed: __("Failed") }; }

class DocReader {
	constructor(wrapper) { this.$b = $(wrapper).find(".layout-main-section"); this.r = null; this.timer = null; }
	stop() { if (this.timer) { clearTimeout(this.timer); this.timer = null; } }
	async start() {
		this.stop(); this.r = null;
		const st = await frappe.xcall(API + "status");
		this.$b.html(`<div class="hkdr"><div class="hkdr-card">
			<p>${__("Upload PDFs or pictures (English or Chinese). Gemini reads them like OCR in the background: you can close this page and come back to the list below.")}</p>
			<p class="text-muted">${__("Results are kept for 30 days. Check the result against the original.")}</p>
			${st.gemini ? "" : `<p><span class="hkdr-flag">${__("No Gemini key is set up: add it in Gmail Settings.")}</span></p>`}
			<button class="btn btn-primary hkdr-big hkdr-take" ${st.gemini ? "" : "disabled"}>${__("Upload PDF or picture")}</button></div>
			<div class="hkdr-list"></div></div>`);
		this.$b.find(".hkdr-take").on("click", () => this.pick());
		this.refresh();
	}
	pick() {
		const uploader = new frappe.ui.FileUploader({
			folder: "Home", make_attachments_public: 0, allow_multiple: true, allow_take_photo: true,
			restrictions: { allowed_file_types: ["image/*", ".pdf"] },
			on_success: async (f) => { await frappe.xcall(API + "submit", { file_url: f.file_url }); this.refresh(); },
		});
	}
	async refresh() {
		this.stop();
		const $l = this.$b.find(".hkdr-list");
		if (!$l.length) return;
		let rows = [];
		try { rows = await frappe.xcall(API + "list_jobs"); } catch (e) { return; }
		$l.html(rows.length ? `<div class="hkdr-card"><h6>${__("Your documents")}</h6><div class="hkdr-wrap"><table>
			<tr><th>${__("File")}</th><th>${__("Status")}</th><th>${__("Sent")}</th><th></th></tr>
			${rows.map((x) => `<tr data-n="${esc(x.name)}"><td>${esc(x.file_name)}</td>
			<td>${esc(statusMap()[x.status] || x.status)}${x.status === "Reading" && x.attempts > 1 ? ` (${__("try {0}", [x.attempts])})` : ""}
			${x.status === "Failed" ? `<br><small class="text-muted">${esc(x.error)}</small>` : ""}</td>
			<td>${esc(frappe.datetime.str_to_user(x.creation))}</td>
			<td>${x.status === "Done" ? `<button class="btn btn-primary btn-xs hkdr-open">${__("Open")}</button> ` : ""}
			${x.status === "Failed" || x.status === "Done" ? `<button class="btn btn-default btn-xs hkdr-retry">${__("Read again")}</button> ` : ""}
			<button class="btn btn-default btn-xs hkdr-del">${__("Delete")}</button></td></tr>`).join("")}</table></div></div>` : "");
		$l.find(".hkdr-open").on("click", (e) => this.open($(e.currentTarget).closest("tr").data("n")));
		$l.find(".hkdr-retry").on("click", async (e) => { await frappe.xcall(API + "retry", { name: $(e.currentTarget).closest("tr").data("n") }); this.refresh(); });
		$l.find(".hkdr-del").on("click", async (e) => { await frappe.xcall(API + "remove", { name: $(e.currentTarget).closest("tr").data("n") }); this.refresh(); });
		if (this.$b.is(":visible") && rows.some((x) => x.status === "Queued" || x.status === "Reading")) this.timer = setTimeout(() => this.refresh(), 5000);
	}
	async open(name) {
		const j = await frappe.xcall(API + "get_job", { name });
		if (!j.data) return;
		this.r = { ...j.data, filename: j.file_name };
		this.draw();
	}
	draw() {
		const r = this.r;
		const tables = r.tables.map((t, i) => `<div class="hkdr-card" data-i="${i}"><h6>${__("Table")} ${i + 1}${t.title ? ": " + esc(t.title) : ""}</h6>
			<button class="btn btn-default btn-sm hkdr-tcopy">${__("Copy (paste into Excel)")}</button>
			<button class="btn btn-default btn-sm hkdr-tcsv">${__("Download CSV")}</button>
			<div class="hkdr-wrap"><table>${t.headers.length ? `<tr>${t.headers.map((h) => `<th>${esc(h)}</th>`).join("")}</tr>` : ""}
			${t.rows.map((row) => `<tr>${row.map((c) => `<td>${esc(c)}</td>`).join("")}</tr>`).join("")}</table></div></div>`).join("");
		this.$b.html(`<div class="hkdr">
			<div class="hkdr-card"><span class="hkdr-flag">${__("Read by {0}", [esc(r.engine)])}</span> <span class="text-muted">${esc(r.filename)}</span>
			${r.unclear.length ? `<p style="margin-top:8px"><b>${__("Hard to read")}:</b> ${r.unclear.map(esc).join("; ")}</p>` : ""}
			<h6 style="margin-top:12px">${__("Text")}</h6><textarea class="hkdr-in hkdr-text" rows="14">${esc(r.text)}</textarea>
			<button class="btn btn-default hkdr-big hkdr-copytext">${__("Copy text")}</button>
			<button class="btn btn-default hkdr-big hkdr-txt">${__("Download text")}</button>
			<button class="btn btn-default hkdr-big hkdr-xlsx">${__("Download Excel (all)")}</button>
			<button class="btn btn-primary hkdr-big hkdr-again">${__("Back to the list")}</button></div>${tables}</div>`);
		const text = () => this.$b.find(".hkdr-text").val();
		this.$b.find(".hkdr-copytext").on("click", () => copy(text()));
		this.$b.find(".hkdr-txt").on("click", () => save("document.txt", new Blob(["﻿" + text()], { type: "text/plain;charset=utf-8" })));
		this.$b.find(".hkdr-xlsx").on("click", async () => {
			const b64 = await frappe.xcall(API + "export_xlsx", { data: { ...this.r, text: text() } });
			const bin = atob(b64), u8 = new Uint8Array(bin.length);
			for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
			save("document.xlsx", new Blob([u8], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }));
		});
		this.$b.find(".hkdr-again").on("click", () => this.start());
		this.$b.find(".hkdr-tcopy").on("click", (e) => copy(tsv(this.r.tables[$(e.currentTarget).closest(".hkdr-card").data("i")])));
		this.$b.find(".hkdr-tcsv").on("click", (e) => {
			const i = $(e.currentTarget).closest(".hkdr-card").data("i");
			save(`table-${i + 1}.csv`, new Blob(["﻿" + csv(this.r.tables[i])], { type: "text/csv;charset=utf-8" }));
		});
	}
}
})();
