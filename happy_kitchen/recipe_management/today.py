"""The "Today" home (desktop icon Today, Custom HTML Block "HK Today").

One call for the whole page: the dashboard part (KPIs, orders by day with the
A4 sheet, waiting on you; dashboard.py) and the board part (happening today,
ordering / receiving / production tasks; today_board.py), merged by the pure
board.merge_today. Each part is only included when the user can read the
doctypes behind it."""

from __future__ import annotations

import frappe

from happy_kitchen.recipe_management import board, dashboard, today_board


@frappe.whitelist()
def today() -> dict:
	return board.merge_today(dashboard.kitchen_today(), today_board.today_board())
