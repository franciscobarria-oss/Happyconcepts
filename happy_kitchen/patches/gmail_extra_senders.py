import frappe


def execute():
	"""Plaza Network sends its orders without the Orders label: read them anyway. Fills a blank only."""
	if not frappe.db.get_single_value("Gmail Settings", "extra_senders"):
		frappe.db.set_single_value("Gmail Settings", "extra_senders", "plaza-network.com")
