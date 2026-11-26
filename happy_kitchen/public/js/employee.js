// Employee form: live preview of the hourly labour cost (the server recalculates it on save,
// hk_operations/team_api.employee_validate) and the "Set clock-in PIN" button.
const HK_MPF_RATE = 0.05;
const HK_MPF_CAP = 1500;

function hk_preview_hourly_cost(frm) {
	const d = frm.doc;
	let cost = 0;
	if (d.hk_hourly_rate) cost = d.hk_hourly_rate * (1 + HK_MPF_RATE);
	else if (d.hk_monthly_base && d.hk_working_days && d.hk_hours_per_day) {
		const mpf = Math.min(d.hk_monthly_base * HK_MPF_RATE, HK_MPF_CAP);
		cost = (d.hk_monthly_base + mpf) / (d.hk_working_days * d.hk_hours_per_day);
	}
	if (frm.fields_dict.hk_hourly_cost) frm.set_value("hk_hourly_cost", Math.round(cost * 100) / 100);
}

frappe.ui.form.on("Employee", {
	hk_monthly_base: hk_preview_hourly_cost,
	hk_hourly_rate: hk_preview_hourly_cost,
	hk_working_days: hk_preview_hourly_cost,
	hk_hours_per_day: hk_preview_hourly_cost,

	refresh(frm) {
		if (frm.is_new() || !frappe.user.has_role(["System Manager", "HR Manager", "HR User"])) return;
		if (frappe.user.has_role(["System Manager", "HR Manager"])) {
			frm.add_custom_button(__("Final pay"), () => hk_final_pay(frm), __("Leaver"));
		}
		frm.add_custom_button(frm.doc.hk_pin_hash ? __("Change clock-in PIN") : __("Set clock-in PIN"), () => {
			frappe.prompt(
				[{ fieldname: "pin", label: __("4-digit PIN"), fieldtype: "Password", reqd: 1 }],
				async ({ pin }) => {
					if (!/^\d{4}$/.test(pin)) return frappe.msgprint(__("The PIN must be exactly 4 digits."));
					await frappe.xcall("happy_kitchen.hk_operations.team_api.set_clock_pin", { employee: frm.doc.name, pin });
					frappe.show_alert({ message: __("PIN set for {0}", [frm.doc.hk_short_name || frm.doc.employee_name]), indicator: "green" });
					frm.reload_doc();
				},
				__("Clock-in PIN"),
				__("Save PIN")
			);
		});
	},
});

function hk_final_pay(frm) {
	frappe.prompt(
		[
			{ fieldname: "last_day", label: __("Last working day"), fieldtype: "Date", reqd: 1, default: frm.doc.relieving_date || frappe.datetime.get_today() },
			{ fieldname: "sh_given", label: __("Statutory holidays already given this year"), fieldtype: "Int", default: 0 },
			{ fieldname: "rest_days_owed", label: __("Rest days still owed (roster)"), fieldtype: "Float", default: 0 },
			{ fieldname: "annual_unused_before", label: __("Unused annual leave from earlier years"), fieldtype: "Float", default: 0 },
			{ fieldname: "avg_daily_wage", label: __("Average daily wage (blank = estimate)"), fieldtype: "Currency" },
		],
		async (v) => {
			const r = await frappe.xcall("happy_kitchen.hk_operations.hr_api.final_pay", { employee: frm.doc.name, ...v });
			const fmt = (x) => (x == null ? "-" : format_currency(x));
			const rows = r.lines
				.map((l) => `<tr><td>${__(l.item)}</td><td class="text-right">${l.days}</td><td class="text-right">${fmt(l.amount)}</td><td class="text-muted small">${frappe.utils.escape_html(l.note)}</td></tr>`)
				.join("");
			frappe.msgprint({
				title: __("Final pay: {0}", [r.employee_name]),
				wide: true,
				message: `<p>${__("Joined")} ${r.joined} &middot; ${__("Last day")} ${r.last_day} &middot; ${__("Daily wage")} ${fmt(r.daily_wage)}</p>
				<table class="table table-bordered"><thead><tr><th>${__("Item")}</th><th>${__("Days")}</th><th>${__("Amount")}</th><th>${__("Basis")}</th></tr></thead><tbody>${rows}
				<tr><th>${__("Total")}</th><th class="text-right">${r.total_days}</th><th class="text-right">${fmt(r.total_amount)}</th><th></th></tr></tbody></table>
				<p class="text-muted small">${__("Estimate for HR to check. Nothing is posted. Annual leave uses completed months and rounds to the nearest day.")}</p>`,
			});
		},
		__("Final pay calculation"),
		__("Work out")
	);
}
