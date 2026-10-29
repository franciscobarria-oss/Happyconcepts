import frappe
from frappe.model.document import Document
from frappe.utils import get_datetime, now_datetime

from happy_kitchen.hk_operations import dates


class OpenedItem(Document):
	def validate(self):
		if not self.opened_at:
			self.opened_at = now_datetime()
		if not self.opened_by:
			self.opened_by = frappe.session.user
		life = frappe.db.get_value(
			"Item", self.item, ["hk_open_life_value", "hk_open_life_unit", "hk_open_storage", "item_name"], as_dict=True
		) or {}
		self.item_name = life.get("item_name") or self.item_name
		self.use_by = dates.opened_use_by(get_datetime(self.opened_at), life.get("hk_open_life_value"), life.get("hk_open_life_unit"))
		if not self.storage:
			self.storage = life.get("hk_open_storage") or ""
		if self.batch_no and not self.lot:
			self.lot = self.batch_no
		if self.status != "Open" and not self.closed_at:
			self.closed_at = now_datetime()
