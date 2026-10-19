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
const hkk_esc = (s) => frappe.utils.escape_html(s == null ? "" : String(s));
const hkk_num = (v, d = 2) => format_number(v || 0, null, d);
const hkk_cur = (v) => format_currency(v || 0, frappe.defaults.get_default("currency"), 2);
// Production screen: pick recipes, set batches, check ingredients, log it.
const HKK_API = "happy_kitchen.recipe_management.kitchen.";

frappe.pages["kitchen-production"].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({ parent: wrapper, title: __("Production"), single_column: true });
	hkk_css();
	wrapper.hkk = new HKKProduction(wrapper);
};
frappe.pages["kitchen-production"].on_page_show = (wrapper) => wrapper.hkk.load();

class HKKProduction {
	constructor(wrapper) {
		this.$b = $(wrapper).find(".layout-main-section");
		this.run = {}; // recipe -> batches
		this.type = "";
		this.q = "";
	}
	async load() {
		this.recipes = await frappe.xcall(HKK_API + "production_recipes");
		this.render();
	}
	render() {
		const types = [["", __("All")], ["Finished Product", __("Finished")], ["Batch Preparation", __("Batch prep")], ["Recipe Component", __("Component")]];
		this.$b.html(`<div class="hkk"><div class="hkk-cols">
			<div>
				<div class="hkk-bar">
					<input class="hkk-input hkk-search" type="search" placeholder="${__("Find recipe")}" value="${hkk_esc(this.q)}">
					<input class="hkk-input hkk-date" type="date" value="${this.date || frappe.datetime.get_today()}" style="width:180px">
				</div>
				<div class="hkk-bar">${types.map(([v, l]) => `<button class="hkk-chip ${this.type === v ? "on" : ""}" data-type="${v}">${l}</button>`).join("")}</div>
				<div class="hkk-tiles"></div>
			</div>
			<div class="hkk-sticky">
				<div class="hkk-card"><h4 style="margin-top:0">${__("Today's run")}</h4><div class="hkk-run"></div></div>
				<div class="hkk-preview"></div>
			</div>
		</div></div>`);
		this.$b.find(".hkk-search").on("input", (e) => { this.q = e.target.value; this.render_tiles(); });
		this.$b.find(".hkk-date").on("change", (e) => { this.date = e.target.value; });
		this.$b.find(".hkk-chip").on("click", (e) => { this.type = $(e.currentTarget).data("type"); this.render(); });
		this.render_tiles();
		this.render_run();
	}
	render_tiles() {
		const q = this.q.trim().toLowerCase();
		const list = this.recipes.filter((r) => (!this.type || r.recipe_type === this.type) && (!q || `${r.recipe_name} ${r.name}`.toLowerCase().includes(q)));
		this.$b.find(".hkk-tiles").html(list.map((r) => `<button class="hkk-tile ${this.run[r.name] ? "sel" : ""}" data-r="${hkk_esc(r.name)}">
			<b>${hkk_esc(r.recipe_name)}</b><small>${hkk_esc(r.name)} · ${__("batch")} ${hkk_num(r.batch_yield, 0)} ${hkk_esc(r.yield_uom || "")}</small></button>`).join("")
			|| `<p class="text-muted">${__("No recipes found")}</p>`);
		this.$b.find(".hkk-tile").on("click", (e) => {
			const r = $(e.currentTarget).data("r");
			this.run[r] = this.run[r] ? this.run[r] : 1;
			this.render_tiles(); this.render_run();
		});
	}
	render_run() {
		const names = Object.keys(this.run);
		const by = Object.fromEntries(this.recipes.map((r) => [r.name, r]));
		const $run = this.$b.find(".hkk-run");
		if (!names.length) {
			$run.html(`<p class="text-muted">${__("Tap a recipe to add it.")}</p>`);
			this.$b.find(".hkk-preview").empty();
			return;
		}
		$run.html(names.map((n) => `<div class="hkk-row" data-r="${hkk_esc(n)}">
			<div><b>${hkk_esc(by[n].recipe_name)}</b><br><small class="text-muted">= ${hkk_num(this.run[n] * by[n].batch_yield, 0)} ${hkk_esc(by[n].yield_uom || "")}</small></div>
			<div class="hkk-step"><button data-d="-1">−</button><input class="hkk-input hkk-num" type="number" inputmode="decimal" step="any" min="0" value="${this.run[n]}" style="width:90px"><button data-d="1">+</button></div>
		</div>`).join("") + `
			<button class="btn btn-default hkk-big hkk-check">${__("Check ingredients")}</button>
			<button class="btn btn-primary hkk-big hkk-log">${__("Log production")}</button>`);
		$run.find(".hkk-step button").on("click", (e) => {
			const n = $(e.currentTarget).closest(".hkk-row").data("r");
			this.run[n] = Math.max(0, (Number(this.run[n]) || 0) + Number($(e.currentTarget).data("d")));
			if (!this.run[n]) delete this.run[n];
			this.render_tiles(); this.render_run();
		});
		$run.find(".hkk-num").on("change", (e) => {
			const n = $(e.currentTarget).closest(".hkk-row").data("r");
			const v = Number(e.target.value);
			if (v > 0) this.run[n] = v; else delete this.run[n];
			this.render_tiles(); this.render_run();
		});
		$run.find(".hkk-check").on("click", () => this.preview());
		$run.find(".hkk-log").on("click", () => this.log());
	}
	entries() {
		return Object.entries(this.run).map(([recipe, batches]) => ({ recipe, batches }));
	}
	async preview() {
		const p = await frappe.xcall(HKK_API + "production_preview", { entries: this.entries() });
		this.$b.find(".hkk-preview").html(`<div class="hkk-card">
			<h4 style="margin-top:0">${__("Ingredients needed")}</h4>
			${p.short_count ? `<div class="hkk-banner warn">${__("{0} ingredient(s) short in stock", [p.short_count])}</div>` : `<div class="hkk-banner ok">${__("Everything is in stock")}</div>`}
			<table class="hkk-table"><tr><th>${__("Ingredient")}</th><th class="hkk-r">${__("Need")}</th><th class="hkk-r">${__("In stock")}</th></tr>
			${p.lines.map((l) => `<tr><td>${hkk_esc(l.item_name)}</td><td class="hkk-r">${hkk_num(l.needed)} ${hkk_esc(l.stock_uom)}</td>
				<td class="hkk-r ${l.short > 0 ? "hkk-bad" : "hkk-ok"}">${hkk_num(l.in_stock)}</td></tr>`).join("")}</table>
			<p class="text-muted" style="margin-top:8px">${__("Ingredient cost")}: <b>${hkk_cur(p.total_cost)}</b></p></div>`);
	}
	log() {
		const n = Object.keys(this.run).length;
		frappe.confirm(__("Log {0} recipe(s) as produced on {1}?", [n, frappe.datetime.str_to_user(this.date || frappe.datetime.get_today())]), async () => {
			const r = await frappe.xcall(HKK_API + "log_production", { entries: this.entries(), posting_date: this.date || frappe.datetime.get_today() });
			frappe.msgprint({
				title: __("Production logged"),
				indicator: "green",
				message: `${r.units.map(([name, units]) => `${hkk_esc(name)}: <b>${hkk_num(units, 0)}</b>`).join("<br>")}
					<br><br>${__("Cost")}: ${hkk_cur(r.total_cost)} · <a href="/app/recipe-production-log/${r.name}">${r.name}</a>`,
			});
			this.run = {};
			this.render();
		});
	}
}
})();
