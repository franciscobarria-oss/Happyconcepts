"""What a fresh Happy Concepts site needs before any feature is installed (P3).
Plain data, no Frappe import, so it can be unit-tested; base.py applies it."""

COMPANY_ABBR = "HK"  # the setup wizard creates "Happy Concepts" with this abbreviation

CURRENCY_PRECISION = 4  # prices are per gram

# name -> must_be_whole_number
UOMS = {"Gram": 0, "Kg": 0, "Nos": 1, "Pack": 1, "Box": 1}

# Warehouse renamed from the wizard's default, then the rest created under "All Warehouses".
WAREHOUSE_RENAMES = {"Stores": "Dry Stock"}
WAREHOUSES = ["Dry Stock", "Fridge", "Freezer", "Finished Goods"]
DEFAULT_WAREHOUSE = "Dry Stock"

# parent -> children (parents are groups under "All Item Groups")
ITEM_GROUPS = {
	"Raw Material": ["Ingredients", "Packaging"],
	"Batch Preparations": ["Doughs", "Cake Bases", "Cooked Proteins", "Sauces & Fillings"],
}
LEAF_ITEM_GROUPS = ["Products"]

# role -> desk access
ROLES = {"Stock Take Approver": 1, "Kitchen Tablet": 1, "Label Printer": 0}

# Starting role profiles (unassigned; pick one on the User record). Roles missing on the site are skipped.
ROLE_PROFILES = {
	"HK Owner": ["System Manager", "Accounts Manager", "Purchase Manager", "Sales Manager", "Stock Manager",
	             "Manufacturing Manager", "HR Manager", "Item Manager", "Stock Take Approver"],
	"HK Purchasing Lead": ["Purchase Manager", "Purchase User", "Stock Manager", "Stock User",
	                       "Manufacturing Manager", "Item Manager", "Employee"],
	"HK Kitchen Staff": ["Stock User", "Manufacturing User", "Employee"],
	"HK Sales Admin": ["Sales Manager", "Sales User", "Accounts User", "Employee"],
	"HK HR Manager": ["HR Manager", "HR User", "Employee"],
}

# Desktop icons the kitchen doesn't use (still reachable by search/URL; untick Hidden to bring one back).
# The Frappe HR ones are replaced by a single "Team" icon in P12.
HIDDEN_DESKTOP_ICONS = [
	"Assets", "Projects", "Quality", "Subcontracting",
	"Frappe HR", "Shift & Attendance", "Leaves", "Performance", "Expenses", "Tenure",
	"Recruitment", "HR Setup", "Payroll", "Tax & Benefits",
]

LANGUAGES_ENABLED = ["zh-TW"]


def with_abbr(name, abbr=COMPANY_ABBR):
	"""'Dry Stock' -> 'Dry Stock - HK' (ERPNext's naming for company-owned records)."""
	suffix = f" - {abbr}"
	return name if name.endswith(suffix) else f"{name}{suffix}"

# Recipe Settings defaults set on a fresh site (only where the field is still empty)
RECIPE_PACKAGING_GROUPS = ["Packaging"]
