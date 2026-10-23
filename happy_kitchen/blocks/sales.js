// Custom HTML Block "HK Sales" (synced from happy_kitchen/blocks/ on migrate), at the top of the
// Selling workspace. Units sold from Sales Orders by delivery date: totals, units per week, SKUs
// sold, and units by weekday over the last 4 weeks of the range (busiest days). The range, the
// drafts switch and the chosen SKU drive one server call (happy_kitchen.hk_operations.sales_api).
// The last range is remembered per device. Runs inside the block's shadow root (`root_element`).
(() => {
	const $ = (sel) => root_element.querySelector(sel);
	const $$ = (sel) => [...root_element.querySelectorAll(sel)];
	const esc = (s) => frappe.utils.escape_html(s == null ? "" : String(s));
	const money = (v) => format_currency(v, frappe.boot.sysdefaults.currency, 0);
	const num = (v) => format_number(v, null, 2).replace(/\.0+$|(\.\d*?)0+$/, "$1");
	const short = (d) => moment(d).format("D MMM");
	const user = (d) => frappe.datetime.str_to_user(d);
	const METHOD = "happy_kitchen.hk_operations.sales_api.sales";
	const STORE = "hk_sales_range";
	const today = frappe.datetime.get_today();

	$$("[data-t]").forEach((el) => (el.textContent = __(el.textContent.trim())));
	$(".search").placeholder = __("Search SKU or name");

	// state: preset (days or "all") or a custom from/to; drafts on/off; one SKU or all
	let state = { days: "84", from: null, to: null, drafts: false, item: null };
	try {
		state = { ...state, ...JSON.parse(localStorage.getItem(STORE) || "{}"), item: null };
	} catch (e) {
		/* private window: not remembered */
	}
	let data = null;
	let seq = 0;

	const range = () => {
		if (state.days === "custom") return [state.from, state.to];
		const to = today;
		if (state.days === "all") return [data && data.first_date ? data.first_date : "2000-01-01", to];
		// whole weeks: start on the Monday, so the first bar is not a part week
		const from = moment(frappe.datetime.add_days(to, 1 - Number(state.days)));
		return [from.subtract((from.day() + 6) % 7, "days").format("YYYY-MM-DD"), to];
	};

	function controls() {
		$$(".presets button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.days === state.days));
		const [from, to] = range();
		$('[name="from"]').value = from || "";
		$('[name="to"]').value = to || "";
		$('[name="drafts"]').checked = !!state.drafts;
	}

	async function load() {
		controls();
		try {
			localStorage.setItem(STORE, JSON.stringify({ days: state.days, from: state.from, to: state.to, drafts: state.drafts }));
		} catch (e) {
			/* not remembered */
		}
		const [from, to] = range();
		const mine = ++seq;
		let r;
		try {
			r = await frappe.call({ method: METHOD, args: {
				from_date: state.days === "all" ? null : from, to_date: to,
				include_drafts: state.drafts ? 1 : 0, item_code: state.item,
				all: state.days === "all" ? 1 : 0,
			} });
		} catch (e) {
			$(".tiles").innerHTML = `<div class="note"><b>${esc(__("Couldn't load the sales figures."))}</b> ${esc(__("Reload the page to try again."))}</div>`;
			return;
		}
		if (mine !== seq) return; // a newer request is on its way
		data = r.message;
		render();
	}

	function render() {
		const d = data;
		controls();
		$('[name="from"]').value = d.from_date;
		$(".range").textContent = `${user(d.from_date)} – ${user(d.to_date)}`;
		$(".filter").hidden = !d.item_code;
		if (d.item_code) $(".filter .item").textContent = `${d.item_code} · ${d.item_name || ""}`;

		// --- tiles ---
		const t = d.totals;
		const tiles = [
			[__("Units sold"), num(t.qty), d.item_code ? d.item_name || d.item_code : __("all SKUs")],
			[__("SKUs sold"), t.skus, __("different items")],
			[__("Orders"), t.orders, d.include_drafts ? __("confirmed and draft") : __("confirmed only")],
			[__("Sales"), money(t.amount), __("net, before tax")],
		];
		$(".tiles").innerHTML = tiles.map(([label, value, detail]) => `<div class="tile">
			<span class="label">${esc(label)}</span><span class="value">${esc(value)}</span><span class="detail">${esc(detail)}</span></div>`).join("");

		const dn = $(".drafts-note");
		dn.hidden = !d.draft_orders;
		dn.className = "note info drafts-note";
		dn.textContent = d.include_drafts
			? __("Includes {0} draft orders in this range (not yet confirmed).", [d.draft_orders])
			: __("{0} draft orders in this range are not counted. Tick Include drafts to add them.", [d.draft_orders]);

		// --- units per week; the last 4 weeks of the range are highlighted ---
		const weeks = d.weeks;
		const peak = Math.max(1, ...weeks.map((w) => w.qty));
		const recentFrom = d.recent ? d.recent.from : null;
		$(".legend").innerHTML = `${esc(__("Monday to Sunday, by delivery date"))}${recentFrom ? `<i></i>${esc(__("last 4 weeks"))}` : ""}`;
		$(".weeks").innerHTML = weeks.length
			? weeks.map((w) => {
				const part = w.week < d.from_date || frappe.datetime.add_days(w.week, 6) > d.to_date;
				const tip = `${__("Week of {0}", [user(w.week)])}: ${num(w.qty)} ${__("units")}, ${__("{0} orders", [w.orders])}, ${money(w.amount)}${part ? " · " + __("part week") : ""}`;
				const cls = ["wkb", recentFrom && w.week >= recentFrom && w.week <= d.recent.to ? "recent" : "", w.qty ? "" : "zero", part ? "part" : ""].join(" ");
				return `<div class="${cls}" title="${esc(tip)}">
					<span class="n">${w.qty ? esc(num(w.qty)) : "0"}</span>
					<span class="col"><i style="height:${Math.round((100 * w.qty) / peak)}%"></i></span>
					<span class="dn">${esc(short(w.week))}</span></div>`;
			}).join("")
			: `<p class="empty">${esc(__("No sales in this range."))}</p>`;
		const wrap = $(".weeks");
		wrap.scrollLeft = wrap.scrollWidth;

		renderSkus();
		renderRecent();
	}

	function renderSkus() {
		const q = ($(".search").value || "").trim().toLowerCase();
		const rows = data.skus.filter((s) => !q || `${s.item_code} ${s.item_name}`.toLowerCase().includes(q));
		$(".skus-count").textContent = data.skus.length;
		$(".skus tbody").innerHTML = rows.length
			? rows.map((s) => `<tr class="sku${s.item_code === data.item_code ? " on" : ""}" data-item="${esc(s.item_code)}" tabindex="0">
				<td><span class="code">${esc(s.item_code)}</span><span class="cap">${esc(s.item_name)}</span>
					<div class="bar"><i style="width:${Math.max(1, Math.round(100 * s.share))}%"></i></div></td>
				<td class="num"><b>${esc(num(s.qty))}</b><span class="cap">${esc(__(s.uom))}</span></td>
				<td class="num">${esc(s.orders)}</td>
				<td class="num">${esc(money(s.amount))}</td></tr>`).join("")
			: `<tr><td colspan="4" class="empty">${esc(q ? __("No SKU matches.") : __("No sales in this range."))}</td></tr>`;
	}

	function renderRecent() {
		const r = data.recent;
		const body = $(".recent-body");
		if (!r) {
			$(".recent-range").textContent = "";
			body.innerHTML = `<p class="empty">${esc(__("No sales in this range."))}</p>`;
			return;
		}
		$(".recent-range").textContent = __("Units by delivery day, {0} to {1}", [user(r.from), user(r.to)]);
		const days = r.weekdays.map((w) => __(w));
		const peak = Math.max(1, ...r.weeks.flatMap((w) => w.days));
		const cell = (v) => {
			const pct = Math.round((100 * v) / peak);
			const style = v ? `background: color-mix(in srgb, var(--k-brand) ${Math.max(8, pct)}%, transparent);${pct > 55 ? " color: var(--k-on-brand);" : ""}` : "";
			return `<td style="${style}">${v ? esc(num(v)) : "·"}</td>`;
		};
		const totPeak = Math.max(...r.totals);
		body.innerHTML = `<table class="heat">
			<thead><tr><th class="wk">${esc(__("Week of"))}</th>${days.map((x) => `<th>${esc(x)}</th>`).join("")}<th>${esc(__("Total"))}</th></tr></thead>
			<tbody>${r.weeks.map((w) => `<tr><th class="wk">${esc(short(w.week))}</th>${w.days.map(cell).join("")}<td class="tot">${esc(num(w.qty))}</td></tr>`).join("")}
			<tr class="sum"><th class="wk">${esc(__("Average"))}</th>${r.average.map((v, i) => `<td${r.totals[i] === totPeak && totPeak ? ' style="color: var(--k-brand)"' : ""}>${esc(num(Math.round(v * 10) / 10))}</td>`).join("")}<td></td></tr>
			</tbody></table>
			<div class="busy">
				<div><div class="label">${esc(__("Busiest weekday"))}</div><div class="value">${esc(r.busiest_weekday ? __(r.busiest_weekday) : "–")}</div>
					<span class="cap">${r.busiest_weekday ? esc(__("{0} units a week on average", [num(Math.round((totPeak / r.weeks.length) * 10) / 10)])) : ""}</span></div>
				<div><div class="label">${esc(__("Busiest date"))}</div><div class="value">${r.busiest_date ? esc(`${__(moment(r.busiest_date.date).format("ddd"))} ${short(r.busiest_date.date)}`) : "–"}</div>
					<span class="cap">${r.busiest_date ? esc(__("{0} units", [num(r.busiest_date.qty)])) : ""}</span></div>
			</div>`;
	}

	// --- events ---
	root_element.addEventListener("click", (e) => {
		const p = e.target.closest(".presets button");
		if (p) {
			state.days = p.dataset.days;
			return load();
		}
		if (e.target.closest(".clear")) {
			state.item = null;
			return load();
		}
		const row = e.target.closest("tr.sku");
		if (row) {
			state.item = row.dataset.item === state.item ? null : row.dataset.item;
			return load();
		}
	});
	root_element.addEventListener("keydown", (e) => {
		const row = e.target.closest && e.target.closest("tr.sku");
		if (row && (e.key === "Enter" || e.key === " ")) {
			e.preventDefault();
			row.click();
		}
	});
	root_element.addEventListener("change", (e) => {
		if (e.target.name === "from" || e.target.name === "to") {
			const from = $('[name="from"]').value;
			const to = $('[name="to"]').value;
			if (!from || !to) return;
			state = { ...state, days: "custom", from: from <= to ? from : to, to: from <= to ? to : from };
			return load();
		}
		if (e.target.name === "drafts") {
			state.drafts = e.target.checked;
			return load();
		}
	});
	$(".search").addEventListener("input", () => data && renderSkus());

	load();
})();
