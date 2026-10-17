"""Runs once after `bench install-app happy_kitchen`.

Base setup (settings, UOMs, warehouses, roles...) is added here in P3. Every step must be
idempotent, because the same functions are re-run from patches on existing sites."""


def after_install():
	pass
