// Custom HTML Block "HK Team Roster" — weekly roster grid. Tap a cell to cycle Off → Early → Late → Off.
// Each cell is one submitted Shift Assignment (start_date = end_date = that day), made on the server
// by hk_operations/team_api.roster_cycle.
(async () => {
	const $ = (sel) => root_element.querySelector(sel);
	const SHIFTS = ["Early", "Late"];
	const SHIFT_HOURS = { Early: 9, Late: 9 }; // = hk_operations/team.SHIFT_TYPES
	const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
	const money = (v) => "$" + Math.round(v).toLocaleString();
	const today = frappe.datetime.get_today();
	const monday = (d) => frappe.datetime.add_days(d, -((frappe.datetime.str_to_obj(d).getDay() + 6) % 7));
	let weekStart = monday(today);
	let state = { emps: [], cells: {}, leave: {} };
	let busy = false;

	const key = (emp, date) => `${emp}|${date}`;

	async function load() {
		const weekEnd = frappe.datetime.add_days(weekStart, 6);
		const [emps, shifts, leave] = await Promise.all([
			frappe.db.get_list("Employee", {
				filters: { status: "Active" },
				fields: ["name", "employee_name", "hk_short_name", "hk_hourly_cost", "department"],
				order_by: "department asc, date_of_joining asc",
				limit: 200,
			}),
			frappe.db.get_list("Shift Assignment", {
				filters: [["docstatus", "=", 1], ["status", "=", "Active"], ["start_date", "between", [weekStart, weekEnd]]],
				fields: ["name", "employee", "shift_type", "start_date"],
				limit: 2000,
			}),
			frappe.db.get_list("Leave Application", {
				filters: [["docstatus", "=", 1], ["status", "=", "Approved"], ["from_date", "<=", weekEnd], ["to_date", ">=", weekStart]],
				fields: ["employee", "from_date", "to_date", "leave_type"],
				limit: 500,
			}),
		]);
		const cells = {};
		for (const s of shifts) cells[key(s.employee, s.start_date)] = s;
		const lv = {};
		for (const l of leave) {
			for (let d = l.from_date; d <= l.to_date; d = frappe.datetime.add_days(d, 1)) lv[key(l.employee, d)] = l.leave_type;
		}
		state = { emps, cells, leave: lv };
		render();
	}

	function render() {
		const dates = DAYS.map((_, i) => frappe.datetime.add_days(weekStart, i));
		const dayTotals = dates.map(() => ({ h: 0, c: 0 }));
		let weekCost = 0;
		const head = `<span></span>` + dates.map((d, i) =>
			`<span class="dh ${d === today ? "today" : ""}">${DAYS[i]}<br><small>${frappe.datetime.str_to_obj(d).getDate()}</small></span>`).join("") +
			`<span class="dh r">Hrs</span><span class="dh r">Cost</span>`;
		const rows = state.emps.map((e) => {
			let hrs = 0;
			const cells = dates.map((d, i) => {
				const k = key(e.name, d);
				if (state.leave[k]) return `<span class="cell lv" title="${frappe.utils.escape_html(state.leave[k])}">Time off</span>`;
				const s = state.cells[k];
				if (!s) return `<button class="cell off" data-emp="${e.name}" data-date="${d}">–</button>`;
				const h = SHIFT_HOURS[s.shift_type] || 9;
				hrs += h;
				dayTotals[i].h += h;
				dayTotals[i].c += h * (e.hk_hourly_cost || 0);
				return `<button class="cell ${s.shift_type === "Early" ? "am" : "pm"}" data-emp="${e.name}" data-date="${d}">${s.shift_type}</button>`;
			}).join("");
			const cost = hrs * (e.hk_hourly_cost || 0);
			weekCost += cost;
			return `<span class="nm" title="${frappe.utils.escape_html(e.employee_name)}">${frappe.utils.escape_html(e.hk_short_name || e.employee_name)}</span>${cells}
				<span class="r">${hrs}</span><span class="r">${money(cost)}</span>`;
		}).join("");
		const foot = `<span class="nm muted">Total</span>` + dayTotals.map((t) => `<span class="ft">${t.h}h<br>${money(t.c)}</span>`).join("") +
			`<span class="r b">${dayTotals.reduce((a, t) => a + t.h, 0)}</span><span class="r b">${money(weekCost)}</span>`;
		$(".grid").innerHTML = head + rows + foot;
		$(".week").textContent = `${frappe.datetime.str_to_user(dates[0])} – ${frappe.datetime.str_to_user(dates[6])}`;
	}

	const API = "happy_kitchen.hk_operations.team_api.";

	async function setCell(emp, date) {
		const k = key(emp, date);
		const r = await frappe.xcall(API + "roster_cycle", { employee: emp, date });
		if (r.shift) state.cells[k] = { name: r.name, employee: emp, shift_type: r.shift, start_date: date };
		else delete state.cells[k];
		render();
		window.dispatchEvent(new Event("hk-roster-changed"));
	}

	function copyLastWeek() {
		frappe.confirm(__("Copy last week's shifts into this week's empty days?"), async () => {
			const n = await frappe.xcall(API + "roster_copy_week", { week_start: weekStart });
			frappe.show_alert({ message: n ? __("{0} shifts copied", [n]) : __("Nothing to copy"), indicator: n ? "green" : "orange" });
			await load();
			window.dispatchEvent(new Event("hk-roster-changed"));
		});
	}

	root_element.addEventListener("click", async (ev) => {
		const cell = ev.target.closest("button.cell");
		if (cell && !busy) {
			busy = true;
			cell.classList.add("saving");
			try { await setCell(cell.dataset.emp, cell.dataset.date); }
			finally { busy = false; }
			return;
		}
		const nav = ev.target.closest("[data-nav]");
		if (nav) {
			const n = nav.dataset.nav;
			weekStart = n === "today" ? monday(today) : frappe.datetime.add_days(weekStart, n === "next" ? 7 : -7);
			return load();
		}
		if (ev.target.closest(".copy")) return copyLastWeek();
	});

	await load();
})();
