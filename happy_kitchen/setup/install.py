"""Runs once after `bench install-app happy_kitchen`. Every step is idempotent, because the
same functions are re-run from patches on existing sites."""

from happy_kitchen.setup import base


def after_install():
	base.apply()
