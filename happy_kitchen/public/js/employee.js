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
