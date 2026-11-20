// Custom HTML Block "HK Kitchen Checks Home": the Kitchen Checks home (Figma "Kitchen checks, tablet
// simplified"): a "Run kitchen checks" card and a tile per management screen, with counts where a count
// makes sense. Counts use frappe.db.count, so each user only gets what their roles may read.
(async () => {
	const $ = (sel) => root_element.querySelector(sel);
	const all = (sel) => root_element.querySelectorAll(sel);
	all("[data-t]").forEach((el) => (el.textContent = __(el.textContent.trim())));
	const TILES = [
		{ label: __("Checklist runs"), route: ["List", "Checklist Run"], count: "Checklist Run" },
		{ label: __("Checklists"), route: ["List", "Checklist Template"], count: "Checklist Template" },
		{ label: __("Schedules"), route: ["List", "Checklist Schedule"], count: "Checklist Schedule" },
		{ label: __("Areas"), route: ["List", "Check Area"], count: "Check Area" },
		{ label: __("Kitchen Checks Log"), route: ["query-report", "Kitchen Checks Log"] },
		{ label: __("Quick picks"), route: ["List", "Corrective Action Preset"], count: "Corrective Action Preset" },
		{ label: __("Settings"), route: ["Form", "Compliance Settings"] },
	];
	const esc = (s) => frappe.utils.escape_html(String(s));
	$(".tiles").innerHTML = TILES.map((t, i) =>
		`<button class="tile" data-i="${i}"><span class="lbl">${esc(t.label)}</span><span class="foot"><b class="n"></b><span class="open">${esc(__("Open"))} →</span></span></button>`).join("");
	root_element.addEventListener("click", (e) => {
		const tile = e.target.closest(".tile");
		if (tile) return frappe.set_route(...TILES[Number(tile.dataset.i)].route);
		if (e.target.closest(".run")) {
			e.preventDefault();
			frappe.set_route("kitchen-checks");
		}
	});
	await Promise.all(TILES.map(async (t, i) => {
		if (!t.count) return;
		try {
			$(`.tile[data-i="${i}"] .n`).textContent = await frappe.db.count(t.count);
		} catch (err) {
			/* no permission to read it: show no number */
		}
	}));
})();
