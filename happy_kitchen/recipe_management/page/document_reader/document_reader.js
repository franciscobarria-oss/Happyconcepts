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

class DocReader {
	constructor(wrapper) { this.$b = $(wrapper).find(".layout-main-section"); this.r = null; }
	async start() {
		this.r = null;
		const st = await frappe.xcall(API + "status");
		this.$b.html(`<div class="hkdr"><div class="hkdr-card">
			<p>${__("Upload a PDF or a picture (English or Chinese). Gemini reads it like OCR and gives you the text and any tables, ready to copy or download.")}</p>
			<p class="text-muted">${__("Nothing is saved except the uploaded file. Check the result against the original.")}</p>
			${st.gemini ? "" : `<p><span class="hkdr-flag">${__("No Gemini key is set up: add it in Gmail Settings.")}</span></p>`}
			<button class="btn btn-primary hkdr-big hkdr-take" ${st.gemini ? "" : "disabled"}>${__("Upload PDF or picture")}</button></div></div>`);
		this.$b.find(".hkdr-take").on("click", () => this.pick());
	}
	pick() {
		new frappe.ui.FileUploader({
			folder: "Home", make_attachments_public: 0, allow_multiple: false, allow_take_photo: true,
			restrictions: { allowed_file_types: ["image/*", ".pdf"] },
			on_success: (f) => this.read(f.file_url, f.file_name),
		});
	}
	async read(url, name) {
		this.$b.html(`<div class="hkdr"><div class="hkdr-card"><p>${__("Reading {0}... this can take up to a minute for long documents.", [esc(name)])}</p></div></div>`);
		try {
			const job = await frappe.xcall(API + "start_read", { file_url: url });
			for (let i = 0; i < 200; i++) {
				await new Promise((ok) => setTimeout(ok, 3000));
				const res = await frappe.xcall(API + "result", { job_id: job });
				if (!res.done) continue;
				if (res.error) throw new Error(res.error);
				this.r = res.data; break;
			}
			if (!this.r) throw new Error("timeout");
		} catch (e) {
			this.$b.html(`<div class="hkdr"><div class="hkdr-card"><p>${__("The file could not be read. Try again, or try a sharper file.")}</p><p class="text-muted">${esc(e && e.message || "")}</p>
				<button class="btn btn-primary hkdr-big hkdr-again">${__("Try another file")}</button></div></div>`);
			this.$b.find(".hkdr-again").on("click", () => this.start());
			return;
		}
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
			<button class="btn btn-primary hkdr-big hkdr-again">${__("Read another file")}</button></div>${tables}</div>`);
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
