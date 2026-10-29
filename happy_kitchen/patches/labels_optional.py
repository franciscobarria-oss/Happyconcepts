"""Labels are optional and never prompted (Francisco, 2026-10-29).

Turns off the two automatic label switches once: Label Settings
"Create labels when a sales order is submitted" and "Print batch labels when
production is logged". Labels stay available from the order's Labels menu and
the production log's "Print batch labels" button. A manager can tick either
switch again later; this patch runs only once per site.
"""

import frappe


def execute():
	if not frappe.db.exists("DocType", "Label Settings"):
		return
	frappe.db.set_single_value("Label Settings", {"create_on_submit": 0, "batch_labels_on_submit": 0})
