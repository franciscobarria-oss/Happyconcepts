from happy_kitchen.hk_operations.current_flag import apply_suffix


def item_validate(doc, method=None):
	"""Item.hk_is_current drives the " (current)" ending of the item name."""
	if doc.item_name:
		doc.item_name = apply_suffix(doc.item_name, doc.get("hk_is_current"))
