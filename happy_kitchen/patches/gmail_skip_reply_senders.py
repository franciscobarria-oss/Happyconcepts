import frappe


def execute():
	"""Our own plain replies (happyconceptsfood.hk, no PDF) are never orders. Fills a blank only."""
	frappe.reload_doc("hk_operations", "doctype", "gmail_settings")
	if not frappe.db.get_single_value("Gmail Settings", "skip_reply_senders"):
		frappe.db.set_single_value("Gmail Settings", "skip_reply_senders", "happyconceptsfood.hk")
