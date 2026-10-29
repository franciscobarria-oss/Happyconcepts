import frappe

from happy_kitchen.patches import supplier_sku_fields


def execute():
	"""Gmail order pick-up: the item search text now also holds customers' external SKUs,
	so relabel the field and refill it. (The Gmail DocTypes come from their JSON on migrate.)"""
	supplier_sku_fields.execute()
	from happy_kitchen.hk_operations import sku

	for parent in frappe.get_all("Item Customer Detail", filters={"parenttype": "Item"}, pluck="parent", distinct=True):
		item = frappe.get_doc("Item", parent)
		rows = [{"supplier": r.supplier, "supplier_part_no": r.supplier_part_no} for r in item.supplier_items]
		rows += [{"supplier": "", "supplier_part_no": r.ref_code} for r in item.customer_items]
		frappe.db.set_value("Item", parent, "hk_supplier_skus", sku.search_text(rows), update_modified=False)
