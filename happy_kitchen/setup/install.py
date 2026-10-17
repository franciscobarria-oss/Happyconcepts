"""Runs once after `bench install-app happy_kitchen`.

Frappe marks every patch in patches.txt as already run on a fresh install, so a fresh site only
gets what after_install does. INSTALL_PATCHES therefore lists every post_model_sync patch
(tests/test_install.py checks this); each one is idempotent and also runs as a patch on existing sites."""

import importlib

INSTALL_PATCHES = [
	"happy_kitchen.patches.base_setup",
	"happy_kitchen.patches.supplier_moq_fields",
]


def after_install():
	for path in INSTALL_PATCHES:
		importlib.import_module(path).execute()
