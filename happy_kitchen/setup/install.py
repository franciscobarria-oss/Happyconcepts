"""Runs once after `bench install-app happy_kitchen`.

Frappe marks every patch in patches.txt as already run on a fresh install, so a fresh site only
gets what after_install does. INSTALL_PATCHES therefore lists every post_model_sync patch
(tests/test_install.py checks this); each one is idempotent and also runs as a patch on existing sites."""

import importlib

INSTALL_PATCHES = [
	"happy_kitchen.patches.base_setup",
	"happy_kitchen.patches.supplier_moq_fields",
	"happy_kitchen.patches.item_recipe_link_fields",
	"happy_kitchen.patches.stock_take_defaults",
	"happy_kitchen.patches.wastage_receiving_setup",
	"happy_kitchen.patches.team_fields",
	"happy_kitchen.patches.team_setup",
	"happy_kitchen.patches.theme_defaults",
	"happy_kitchen.patches.labels_setup",
	"happy_kitchen.patches.label_design_defaults",
	"happy_kitchen.patches.date_tracking_setup",
]


def after_install():
	for path in INSTALL_PATCHES:
		importlib.import_module(path).execute()
	# install-app doesn't run after_migrate, so create the Custom HTML Blocks now too
	from happy_kitchen.setup import blocks

	blocks.sync()
