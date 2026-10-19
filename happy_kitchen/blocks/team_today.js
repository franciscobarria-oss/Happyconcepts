// Custom HTML Block "HK Team Today" — summary cards and "Waiting for you" (time off to approve, certs expiring).
// Runs inside the block's shadow root; `root_element` is provided by Frappe.
(async () => {
	const $ = (sel) => root_element.querySelector(sel);
	const today = frappe.datetime.get_today();
	const SHIFT_HOURS = { Early: 9, Late: 9 };
	const SHIFT_START = { Early: "07:00", Late: "11:00" };
	const LATE_GRACE_MIN = 10;
	const money = (v) => "$" + Math.round(v).toLocaleString();
	const monday = (d) => {
		const dt = frappe.datetime.str_to_obj(d);
		const back = (dt.getDay() + 6) % 7;
		return frappe.datetime.add_days(d, -back);
	};

	async function load() {
		$(".date").textContent = moment(today).format("dddd D MMMM");
		const weekStart = monday(today);
		const weekEnd = frappe.datetime.add_days(weekStart, 6);
		const [emps, shifts, checkins, openLeave, onLeave] = await Promise.all([
			frappe.db.get_list("Employee", {
				filters: { status: "Active" },
				fields: ["name", "employee_name", "hk_short_name", "hk_hourly_cost", "hk_cert_expiry"],
				limit: 200,
			}),
			frappe.db.get_list("Shift Assignment", {
				filters: [["docstatus", "=", 1], ["status", "=", "Active"], ["start_date", "between", [weekStart, weekEnd]]],
				fields: ["employee", "shift_type", "start_date"],
				limit: 1000,
			}),
			frappe.db.get_list("Employee Checkin", {
				filters: [["time", ">=", today + " 00:00:00"]],
				fields: ["employee", "log_type", "time"],
				order_by: "time asc",
				limit: 1000,
			}),
			frappe.db.get_list("Leave Application", {
				filters: { docstatus: 0, status: "Open" },
				fields: ["name", "employee", "employee_name", "leave_type", "from_date", "to_date", "total_leave_days"],
				order_by: "from_date asc",
				limit: 50,
			}),
			frappe.db.get_list("Leave Application", {
				filters: [["docstatus", "=", 1], ["status", "=", "Approved"], ["from_date", "<=", today], ["to_date", ">=", today]],
				fields: ["employee"],
				limit: 200,
			}),
		]);
		const emp = Object.fromEntries(emps.map((e) => [e.name, e]));
		const short = (id) => (emp[id] && (emp[id].hk_short_name || emp[id].employee_name)) || id;
		const off = new Set(onLeave.map((l) => l.employee));

		const todayShifts = shifts.filter((s) => s.start_date === today && !off.has(s.employee) && emp[s.employee]);
		const lastLog = {};
		const worked = {};
		for (const c of checkins) {
			if (c.log_type === "IN") lastLog[c.employee] = c;
			else if (lastLog[c.employee] && lastLog[c.employee].log_type === "IN") {
				const h = (frappe.datetime.str_to_obj(c.time) - frappe.datetime.str_to_obj(lastLog[c.employee].time)) / 36e5;
				worked[c.employee] = (worked[c.employee] || 0) + h;
				lastLog[c.employee] = c;
			} else lastLog[c.employee] = c;
		}
		const now = frappe.datetime.str_to_obj(frappe.datetime.now_datetime());
		for (const [id, log] of Object.entries(lastLog)) {
			if (log.log_type === "IN") worked[id] = (worked[id] || 0) + (now - frappe.datetime.str_to_obj(log.time)) / 36e5;
		}
		const clockedIn = Object.values(lastLog).filter((l) => l.log_type === "IN").length;
		const late = todayShifts.filter((s) => {
			if (lastLog[s.employee]) return false;
			const start = frappe.datetime.str_to_obj(`${today} ${SHIFT_START[s.shift_type] || "00:00"}:00`);
			return now - start > LATE_GRACE_MIN * 6e4;
		});
		const plannedToday = todayShifts.reduce((t, s) => t + (SHIFT_HOURS[s.shift_type] || 9) * (emp[s.employee].hk_hourly_cost || 0), 0);
		const hoursToday = todayShifts.reduce((t, s) => t + (SHIFT_HOURS[s.shift_type] || 9), 0);
		const actualToday = Object.entries(worked).reduce((t, [id, h]) => t + h * ((emp[id] && emp[id].hk_hourly_cost) || 0), 0);
		const plannedWeek = shifts.filter((s) => emp[s.employee])
			.reduce((t, s) => t + (SHIFT_HOURS[s.shift_type] || 9) * (emp[s.employee].hk_hourly_cost || 0), 0);

		$(".metrics").innerHTML = `
			<div class="m"><p class="l">On shift today 今日當值</p><p class="v">${todayShifts.length} <span>of ${emps.length}</span></p>
				<p class="s">${off.size ? off.size + " on time off" : "&nbsp;"}</p></div>
			<div class="m"><p class="l">Clocked in 已打卡</p><p class="v">${clockedIn}</p>
				<p class="s ${late.length ? "warn" : ""}">${late.length ? late.map((s) => short(s.employee)).join(", ") + " not in yet" : "Everyone on time"}</p></div>
			<div class="m"><p class="l">Labour today</p><p class="v">${money(plannedToday)}</p>
				<p class="s">${hoursToday} hrs planned · ${money(actualToday)} so far</p></div>
			<div class="m"><p class="l">Labour this week</p><p class="v">${money(plannedWeek)}</p>
				<p class="s">Planned from the roster</p></div>`;

		const items = [];
		for (const l of openLeave) {
			items.push(`<div class="row" data-leave="${l.name}">
				<div class="av">${frappe.utils.escape_html(short(l.employee).slice(0, 2).toUpperCase())}</div>
				<div class="grow"><p>${frappe.utils.escape_html(short(l.employee))} · ${frappe.utils.escape_html(l.leave_type)}</p>
				<p class="s">${frappe.datetime.str_to_user(l.from_date)} – ${frappe.datetime.str_to_user(l.to_date)} · ${l.total_leave_days} day(s)</p></div>
				<button class="btn btn-xs btn-default" data-act="Approved">Approve</button>
				<button class="btn btn-xs btn-default" data-act="Rejected">Decline</button></div>`);
		}
		const soon = frappe.datetime.add_days(today, 30);
		for (const e of emps.filter((e) => e.hk_cert_expiry && e.hk_cert_expiry <= soon)) {
			const days = frappe.datetime.get_day_diff(e.hk_cert_expiry, today);
			items.push(`<div class="row"><div class="av warn">${frappe.utils.escape_html(short(e.name).slice(0, 2).toUpperCase())}</div>
				<div class="grow"><p>${frappe.utils.escape_html(short(e.name))} · hygiene cert</p>
				<p class="s ${days < 0 ? "warn" : ""}">${days < 0 ? "Expired " + -days + " days ago" : "Expires in " + days + " days"}</p></div>
				<a class="btn btn-xs btn-default" href="/desk/employee/${encodeURIComponent(e.name)}">Update</a></div>`);
		}
		$(".waiting").innerHTML = items.length ? items.join("") : `<p class="s">Nothing to approve. You're all caught up.</p>`;
	}

	root_element.addEventListener("click", async (ev) => {
		const btn = ev.target.closest("button[data-act]");
		if (btn) {
			const name = btn.closest("[data-leave]").dataset.leave;
			btn.disabled = true;
			const doc = (await frappe.call("frappe.client.get", { doctype: "Leave Application", name })).message;
			doc.status = btn.dataset.act;
			await frappe.call("frappe.client.submit", { doc });
			frappe.show_alert({ message: btn.dataset.act === "Approved" ? "Time off approved" : "Time off declined", indicator: "green" });
			return load();
		}
		if (ev.target.closest(".book")) return hk_book_time_off(load);
	});

	window.hk_book_time_off = async function (after) {
		const emps = await frappe.db.get_list("Employee", { filters: { status: "Active" }, fields: ["name", "employee_name", "hk_short_name"], limit: 200 });
		const d = new frappe.ui.Dialog({
			title: "Book time off",
			fields: [
				{ fieldname: "employee", label: "Who", fieldtype: "Select", reqd: 1,
				  options: emps.map((e) => ({ value: e.name, label: `${e.hk_short_name || ""} (${e.employee_name})` })) },
				{ fieldname: "leave_type", label: "Type", fieldtype: "Select", reqd: 1, default: "Annual Leave",
				  options: ["Annual Leave", "Sick Leave", "Leave Without Pay"] },
				{ fieldname: "from_date", label: "From", fieldtype: "Date", reqd: 1, default: frappe.datetime.get_today() },
				{ fieldname: "to_date", label: "To", fieldtype: "Date", reqd: 1, default: frappe.datetime.get_today() },
				{ fieldname: "half_day", label: "Half day", fieldtype: "Check" },
				{ fieldname: "reason", label: "Note", fieldtype: "Small Text" },
			],
			primary_action_label: "Book",
			async primary_action(v) {
				if (v.to_date < v.from_date) return frappe.msgprint("The end date is before the start date.");
				const company = frappe.defaults.get_default("company");
				await frappe.call("frappe.client.insert", { doc: {
					doctype: "Leave Application", employee: v.employee, leave_type: v.leave_type, company,
					from_date: v.from_date, to_date: v.to_date, half_day: v.half_day ? 1 : 0,
					half_day_date: v.half_day ? v.from_date : null, description: v.reason,
					status: "Approved", docstatus: 1,
				} });
				d.hide();
				frappe.show_alert({ message: "Time off booked", indicator: "green" });
				after && after();
			},
		});
		d.show();
	};

	window.__hkTodayLoad = load;
	if (!window.__hkTodayBound) {
		window.addEventListener("hk-roster-changed", () => window.__hkTodayLoad && window.__hkTodayLoad());
		window.__hkTodayBound = true;
	}
	clearInterval(window.__hkTodayTimer);
	window.__hkTodayTimer = setInterval(() => root_element.isConnected !== false && load(), 120000);
	await load();
})();
