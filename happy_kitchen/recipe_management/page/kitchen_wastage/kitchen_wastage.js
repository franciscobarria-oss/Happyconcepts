// Copyright (c) 2026, Happy Kitchen and contributors
// Each kitchen screen keeps its helpers in its own scope, so several can load in one session.
(() => {
// Shared look for the kitchen screens (large touch targets; English or 繁體中文 via the EN / 中 toggle).
function hkk_css() {
	if (document.getElementById("hkk-css")) return;
	$(`<style id="hkk-css">
	.hkk { max-width: 1100px; margin: 0 auto; padding-bottom: 90px; }
	.hkk h4 { margin: 18px 0 10px; font-weight: 700; }
	.hkk-bar { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; margin: 6px 0 12px; }
	.hkk-input, .hkk-select { min-height: 52px; font-size: 18px; padding: 8px 14px; border-radius: 12px; border: 1px solid var(--border-color); background: var(--control-bg); }
	.hkk-input.hkk-num { width: 130px; text-align: right; font-size: 22px; }
	.hkk-search { flex: 1; min-width: 220px; }
	.hkk-chip { min-height: 44px; padding: 8px 16px; border-radius: 22px; border: 1px solid var(--border-color); background: var(--card-bg); font-size: 16px; }
	.hkk-chip.on { background: var(--primary); color: var(--hk-on-brand, #fff); border-color: var(--primary); }
	.hkk-tiles { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 12px; }
	.hkk-tile { text-align: left; min-height: 96px; padding: 12px 14px; border-radius: 14px; border: 1px solid var(--border-color); background: var(--card-bg); font-size: 16px; line-height: 1.3; }
	.hkk-tile b { display: block; font-size: 17px; }
	.hkk-tile small { color: var(--text-muted); }
	.hkk-tile.sel { outline: 3px solid var(--primary); }
	.hkk-card { border: 1px solid var(--border-color); border-radius: 14px; padding: 14px 16px; background: var(--card-bg); margin-bottom: 12px; }
	.hkk-row { display: grid; grid-template-columns: 1fr auto; gap: 10px; align-items: center; padding: 10px 0; border-bottom: 1px solid var(--border-color); font-size: 17px; }
	.hkk-row:last-child { border-bottom: 0; }
	.hkk-step { display: inline-flex; align-items: center; gap: 6px; }
	.hkk-step button { width: 52px; height: 52px; border-radius: 12px; font-size: 26px; border: 1px solid var(--border-color); background: var(--card-bg); }
	.hkk-big { width: 100%; min-height: 62px; font-size: 20px; border-radius: 14px; margin-top: 14px; }
	.hkk-table { width: 100%; font-size: 16px; } .hkk-table td, .hkk-table th { padding: 10px 8px; border-bottom: 1px solid var(--border-color); }
	.hkk-table th { font-weight: 600; color: var(--text-muted); font-size: 13px; }
	.hkk-r { text-align: right; white-space: nowrap; }
	.hkk-bad { color: var(--hk-danger, var(--red-600, #c53030)); font-weight: 700; } .hkk-ok { color: var(--hk-success, var(--green-600, #2f855a)); }
	.hkk-flag { display: inline-block; background: var(--hk-warning-soft, var(--orange-100, #feebc8)); color: var(--hk-warning, var(--orange-800, #9c4221)); border-radius: 10px; padding: 2px 10px; margin: 2px 4px 2px 0; font-size: 14px; }
	.hkk-banner { padding: 14px 16px; border-radius: 12px; margin: 10px 0; font-size: 16px; background: var(--bg-light-gray); }
	.hkk-banner.ok { background: var(--hk-success-soft, var(--green-50, #f0fff4)); border: 1px solid var(--hk-success-soft, var(--green-300, #9ae6b4)); }
	.hkk-banner.warn { background: var(--hk-warning-soft, var(--orange-50, #fffaf0)); border: 1px solid var(--hk-warning-soft, var(--orange-300, #fbd38d)); }
	.hkk-cols { display: grid; grid-template-columns: 1.6fr 1fr; gap: 18px; align-items: start; }
	.hkk-sticky { position: sticky; top: calc(var(--navbar-height, 48px) + 10px); }
	@media (max-width: 900px) { .hkk-cols { grid-template-columns: 1fr; } .hkk-sticky { position: static; } }
	</style>`).appendTo("head");
}
const HKK_ZH = (frappe.boot.lang || "").startsWith("zh");
const hkk_esc = (s) => frappe.utils.escape_html(s == null ? "" : String(s));
const hkk_num = (v, d = 2) => format_number(v || 0, null, d);
const hkk_cur = (v) => format_currency(v || 0, frappe.defaults.get_default("currency"), 2);
// Wastage screen: find item -> qty -> reason -> add; submit the list.
const HKK_API = "happy_kitchen.recipe_management.kitchen.";
const HKK_WST_KEY = "hk-wastage-pending";

frappe.pages["kitchen-wastage"].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({ parent: wrapper, title: __("Log Wastage"), single_column: true });
	hkk_css();
	wrapper.hkk = new HKKWastage(wrapper);
};
frappe.pages["kitchen-wastage"].on_page_show = (wrapper) => wrapper.hkk.load();

class HKKWastage {
	constructor(wrapper) {
		this.$b = $(wrapper).find(".layout-main-section");
		this.sel = null;
	}
	get list() {
		try { return JSON.parse(localStorage.getItem(HKK_WST_KEY) || "[]"); } catch (e) { return this._list || []; }
	}
	set list(v) {
		this._list = v;
		try { localStorage.setItem(HKK_WST_KEY, JSON.stringify(v)); } catch (e) { /* storage blocked: keep in memory */ }
	}
	async load() {
		this.reasons = await frappe.xcall(HKK_API + "wastage_reasons");
		this.render();
	}
	render() {
		this.$b.html(`<div class="hkk"><div class="hkk-cols">
			<div>
				<div class="hkk-bar"><input class="hkk-input hkk-search" type="search" placeholder="${__("Find item")}"></div>
				<div class="hkk-tiles hkk-results"></div>
				<div class="hkk-entry"></div>
			</div>
			<div class="hkk-sticky"><div class="hkk-card"><h4 style="margin-top:0">${__("To submit")}</h4><div class="hkk-list"></div></div></div>
		</div></div>`);
		let t;
		this.$b.find(".hkk-search").on("input", (e) => { clearTimeout(t); t = setTimeout(() => this.search(e.target.value), 250); });
		this.search("");
		this.render_list();
	}
	async search(txt) {
		const items = await frappe.xcall(HKK_API + "find_items", { txt, limit: 24 });
		this.$b.find(".hkk-results").html(items.map((i) => `<button class="hkk-tile" data-i='${hkk_esc(JSON.stringify(i))}'>
			<b>${hkk_esc(i.item_name)}</b><small>${hkk_esc(i.name)} · ${hkk_esc(i.stock_uom)}</small></button>`).join("")
			|| `<p class="text-muted">${__("Nothing found")}</p>`);
		this.$b.find(".hkk-results .hkk-tile").on("click", (e) => { this.sel = JSON.parse($(e.currentTarget).attr("data-i")); this.render_entry(); });
	}
	render_entry() {
		const i = this.sel;
		const units = i.stock_uom === "Nos" ? ["piece"] : ["g", "kg"];
		this.reason = this.reason || (this.reasons[0] && this.reasons[0].name);
		this.$b.find(".hkk-entry").html(`<div class="hkk-card" style="margin-top:14px">
			<h4 style="margin-top:0">${hkk_esc(i.item_name)} <small class="text-muted">${hkk_esc(i.name)}</small></h4>
			<div class="hkk-bar">
				<input class="hkk-input hkk-num hkk-qty" type="number" inputmode="decimal" step="any" min="0" placeholder="0">
				<select class="hkk-select hkk-uom">${units.map((u) => `<option>${u}</option>`).join("")}</select>
			</div>
			<div class="hkk-bar">${this.reasons.map((r) => `<button class="hkk-chip ${this.reason === r.name ? "on" : ""}" data-r="${hkk_esc(r.name)}">${hkk_esc(HKK_ZH && r.reason_zh ? r.reason_zh : __(r.name))}</button>`).join("")}</div>
			<input class="hkk-input hkk-note" style="width:100%" placeholder="${__("Note (optional)")}">
			<button class="btn btn-primary hkk-big hkk-add">${__("Add")}</button></div>`);
		const $e = this.$b.find(".hkk-entry");
		$e.find(".hkk-qty").trigger("focus");
		$e.find(".hkk-chip").on("click", (ev) => { this.reason = $(ev.currentTarget).data("r"); $e.find(".hkk-chip").removeClass("on"); $(ev.currentTarget).addClass("on"); });
		$e.find(".hkk-add").on("click", () => {
			const qty = Number($e.find(".hkk-qty").val());
			if (!(qty > 0)) return frappe.show_alert({ message: __("Enter a quantity"), indicator: "orange" });
			if (!this.reason) return frappe.show_alert({ message: __("Choose a reason"), indicator: "orange" });
			this.list = this.list.concat([{ item: i.name, item_name: i.item_name, qty, uom: $e.find(".hkk-uom").val(), reason: this.reason, notes: $e.find(".hkk-note").val() }]);
			this.sel = null;
			$e.empty();
			this.render_list();
		});
	}
	render_list() {
		const l = this.list;
		const $l = this.$b.find(".hkk-list");
		if (!l.length) return $l.html(`<p class="text-muted">${__("Nothing yet.")}</p>`);
		$l.html(l.map((x, k) => `<div class="hkk-row"><div><b>${hkk_esc(x.item_name)}</b><br><small class="text-muted">${hkk_num(x.qty)} ${hkk_esc(x.uom)} · ${hkk_esc(x.reason)}${x.notes ? " · " + hkk_esc(x.notes) : ""}</small></div>
			<button class="btn btn-default btn-sm hkk-del" data-k="${k}">✕</button></div>`).join("") +
			`<button class="btn btn-primary hkk-big hkk-submit">${__("Submit {0} item(s)", [l.length])}</button>`);
		$l.find(".hkk-del").on("click", (e) => { const k = Number($(e.currentTarget).data("k")); this.list = this.list.filter((_, i) => i !== k); this.render_list(); });
		$l.find(".hkk-submit").on("click", () => this.submit());
	}
	submit() {
		frappe.confirm(__("Submit this wastage? It will be taken out of stock."), async () => {
			const r = await frappe.xcall(HKK_API + "log_wastage", { lines: this.list.map(({ item, qty, uom, reason, notes }) => ({ item, qty, uom, reason, notes })) });
			this.list = [];
			this.render_list();
			frappe.msgprint({
				title: __("Wastage logged"),
				indicator: r.stock_note ? "orange" : "green",
				message: `${__("Cost")}: <b>${hkk_cur(r.total_cost)}</b> · <a href="/app/wastage-log/${r.name}">${r.name}</a>${r.stock_note ? `<br><br>${hkk_esc(r.stock_note)}` : ""}`,
			});
		});
	}
}
})();
