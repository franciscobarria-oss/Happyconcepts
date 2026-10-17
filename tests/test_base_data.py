from happy_kitchen.setup import base_data as d


def test_with_abbr():
	assert d.with_abbr("Dry Stock") == "Dry Stock - HK"
	assert d.with_abbr("Dry Stock - HK") == "Dry Stock - HK"
	assert d.with_abbr("Fridge", "XY") == "Fridge - XY"


def test_currency_precision_is_four():
	assert d.CURRENCY_PRECISION == 4


def test_warehouses():
	assert d.DEFAULT_WAREHOUSE in d.WAREHOUSES
	assert set(d.WAREHOUSE_RENAMES.values()) <= set(d.WAREHOUSES)
	assert {"Dry Stock", "Fridge", "Freezer", "Finished Goods"} <= set(d.WAREHOUSES)


def test_item_groups_unique():
	names = list(d.ITEM_GROUPS) + [c for cs in d.ITEM_GROUPS.values() for c in cs] + d.LEAF_ITEM_GROUPS
	assert len(names) == len(set(names))
	assert d.ITEM_GROUPS["Raw Material"] == ["Ingredients", "Packaging"]


def test_role_profiles_only_use_known_or_own_roles():
	own = set(d.ROLES)
	assert "Stock Take Approver" in d.ROLE_PROFILES["HK Owner"]
	for roles in d.ROLE_PROFILES.values():
		assert len(roles) == len(set(roles))
	assert own == {"Stock Take Approver", "Kitchen Tablet", "Label Printer"}
	assert d.ROLES["Label Printer"] == 0


def test_whole_number_uoms():
	assert d.UOMS["Nos"] == 1 and d.UOMS["Gram"] == 0
