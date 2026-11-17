"""hr_setup already ran on hcl-erp but its checklist templates were not made (they need a title).
hr_setup is idempotent, so run it again; it only adds what is missing."""

from happy_kitchen.patches import hr_setup


def execute():
	hr_setup.execute()
