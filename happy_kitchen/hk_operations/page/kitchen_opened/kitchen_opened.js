// Copyright (c) 2026, Happy Kitchen and contributors
// Opened screen for the iPad: search or scan an item, pick the lot, print the small USE BY label.
(() => {
const API = "happy_kitchen.hk_operations.dates_api.";
const esc = (s) => frappe.utils.escape_html(s == null ? "" : String(s));

function css() {
	if (document.getElementById("hko-css")) return;
	$(`<style id="hko-css">
	.hko { max-width: 760px; margin: 0 auto; padding-bottom: 80px; }
	.hko-input { min-height: 56px; font-size: 20px; padding: 8px 14px; border-radius: 12px; border: 1px solid var(--border-color); background: var(--control-bg); width: 100%; }
	.hko-tiles { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; margin: 12px 0; }
	.hko-tile { text-align: left; min-height: 64px; padding: 10px 14px; border-radius: 14px; border: 1px solid var(--border-color); background: var(--card-bg); font-size: 16px; }
	.hko-card { border: 1px solid var(--border-color); border-radius: 14px; padding: 16px; background: var(--card-bg); margin: 12px 0; }
	.hko-card h3 { margin: 0 0 4px; }
	.hko-row { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; margin: 12px 0; }
	.hko-step button { width: 56px; height: 56px; border-radius: 12px; font-size: 28px; border: 1px solid var(--border-color); background: var(--card-bg); }
	.hko-step span { display: inline-block; min-width: 44px; text-align: center; font-size: 26px; font-weight: 700; }
	.hko-go { width: 100%; min-height: 66px; font-size: 22px; border-radius: 14px; }
	.hko-muted { color: var(--text-muted); }
	.hko-recent td { padding: 8px 6px; border-bottom: 1px solid var(--border-color); }
	</style>`).appendTo("head");
}

frappe.pages["kitchen-opened"].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({ parent: wrapper, title: __("Opened Items"), single_column: true });
	css();
	wrapper.hko = new Opened(wrapper);
};
frappe.pages["kitchen-opened"].on_page_show = (wrapper) => wrapper.hko.show();

class Opened {
	constructor(wrapper) {
		this.$b = $(wrapper).find(".layout-main-section");
		this.item = null;
		this.labels = 1;
		this.$b.html(`<div class="hko">
			<input class="hko-input" type="search" autocomplete="off" placeholder="${__("Scan or search an item")}">
			<div class="hko-tiles"></div><div class="hko-pick"></div>
			<h5 style="margin-top:24px">${__("Opened today")}</h5><div class="hko-recent"></div></div>`);
		let t;
		this.$q = this.$b.find(".hko-input");
		this.$q.on("input", () => { clearTimeout(t); t = setTimeout(() => this.search(), 250); });
		this.$q.on("keydown", (e) => { if (e.key === "Enter") this.scan(); });
	}
	show() { this.$q.trigger("focus"); this.recent(); }
	async scan() {
		const code = this.$q.val().trim();
		if (!code) return;
		const item = await frappe.xcall(API + "find_item", { code });
		if (item) { this.choose(item); this.$q.val(""); this.$b.find(".hko-tiles").empty(); }
		else this.search();
	}
	async search() {
		const txt = this.$q.val().trim();
		const $t = this.$b.find(".hko-tiles").empty();
		if (txt.length < 2) return;
		const rows = await frappe.xcall("happy_kitchen.recipe_management.kitchen.find_items", { txt, limit: 12 });
		rows.forEach((r) => $(`<button class="hko-tile"><b>${esc(r.item_name)}</b><br><small class="hko-muted">${esc(r.name)}</small></button>`)
			.on("click", async () => { this.choose(await frappe.xcall(API + "find_item", { code: r.name })); })
			.appendTo($t));
		if (!rows.length) $t.html(`<div class="hko-muted">${__("No item found")}</div>`);
	}
	choose(item) {
		this.item = item; this.labels = 1;
		const $p = this.$b.find(".hko-pick");
		if (!item.open_life_set) {
			$p.html(`<div class="hko-card">${__("Set 'Expiry after opening' on {0} first (Item > Label tab).", [esc(item.item_name)])}</div>`);
			return;
		}
		const lots = (item.lots || []).map((l) => `<option value="${esc(l.batch_no || "")}|${esc(l.lot)}">${esc(l.lot)} · ${esc(l.use_by || "")}</option>`).join("");
		$p.html(`<div class="hko-card"><h3>${esc(item.item_name)}</h3>
			<div class="hko-muted">${__("Keeps {0} {1} once opened", [item.hk_open_life_value, __(item.hk_open_life_unit)])}</div>
			${lots ? `<div class="hko-row"><label>${__("Batch")}</label><select class="hko-input hko-lot" style="width:auto"><option value="|">${__("No batch")}</option>${lots}</select></div>` : ""}
			<div class="hko-row hko-step"><label>${__("Labels")}</label><button data-d="-1">−</button><span class="hko-n">1</span><button data-d="1">+</button></div>
			<button class="btn btn-primary hko-go">${__("Open and print label")}</button></div>`);
		$p.find(".hko-step button").on("click", (e) => {
			this.labels = Math.max(1, this.labels + Number($(e.currentTarget).data("d")));
			$p.find(".hko-n").text(this.labels);
		});
		$p.find(".hko-go").on("click", () => this.go());
	}
	async go() {
		const [batch_no, lot] = (this.$b.find(".hko-lot").val() || "|").split("|");
		const r = await frappe.xcall(API + "open_item", { item: this.item.name, labels: this.labels, batch_no, lot });
		frappe.show_alert({ message: r.printer ? __("Label queued. Use by {0}", [r.use_by]) : __("Saved, but no kitchen label printer is set up"), indicator: r.printer ? "green" : "orange" });
		this.item = null;
		this.$b.find(".hko-pick").empty();
		this.$q.val("").trigger("focus");
		this.recent();
	}
	async recent() {
		const rows = await frappe.xcall("frappe.client.get_list", {
			doctype: "Opened Item", filters: { opened_at: [">=", frappe.datetime.get_today()] },
			fields: ["name", "item_name", "use_by", "status"], order_by: "opened_at desc", limit_page_length: 15,
		});
		const $r = this.$b.find(".hko-recent");
		$r.html(rows.length ? `<table class="hko-recent" style="width:100%">${rows.map((o) =>
			`<tr><td>${esc(o.item_name)}</td><td>${esc(frappe.datetime.str_to_user(o.use_by))}</td><td>${__(o.status)}</td>
			<td><a href="/app/opened-item/${encodeURIComponent(o.name)}">${__("Open")}</a></td></tr>`).join("")}</table>` : `<div class="hko-muted">${__("Nothing opened yet today")}</div>`);
	}
}
})();
