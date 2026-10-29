def ensure_key():
	"""Give the site its encryption key now. Frappe only makes one the first time a Password field is
	saved, and two workers doing that at once end with a key that can't read the secret."""
	from frappe.utils.password import get_encryption_key

	get_encryption_key()


def execute():
	ensure_key()
