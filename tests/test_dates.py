import os
import sys
from datetime import date, datetime

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from happy_kitchen.hk_operations import date_labels as dl  # noqa: E402
from happy_kitchen.hk_operations import dates  # noqa: E402

OPENED = datetime(2026, 10, 19, 14, 30, 45)


def test_hours_count_from_the_minute_opened():
	assert dates.opened_use_by(OPENED, 4, "Hours") == datetime(2026, 10, 19, 18, 30)
	assert dates.opened_use_by(OPENED, 1.5, "Hours") == datetime(2026, 10, 19, 16, 0)
	# past midnight
	assert dates.opened_use_by(OPENED, 12, "Hours") == datetime(2026, 10, 20, 2, 30)


def test_days_end_at_the_end_of_the_last_day_and_count_the_opening_day():
	assert dates.opened_use_by(OPENED, 1, "Days") == datetime(2026, 10, 19, 23, 59)
	assert dates.opened_use_by(OPENED, 3, "Days") == datetime(2026, 10, 21, 23, 59)
	assert dates.opened_use_by(OPENED, 2.7, "Days") == datetime(2026, 10, 20, 23, 59)  # whole days only
	assert dates.opened_use_by(OPENED, 0.5, "Days") == datetime(2026, 10, 19, 23, 59)  # at least the day itself
	assert dates.opened_use_by(OPENED, 3, None) == datetime(2026, 10, 21, 23, 59)  # unit defaults to days


def test_no_open_life_means_no_use_by():
	for value in (0, None, "", -2, "x"):
		assert dates.opened_use_by(OPENED, value, "Days") is None


def test_batch_use_by_and_lots():
	assert dates.batch_use_by(date(2026, 10, 19), 5) == date(2026, 10, 24)
	assert dates.batch_use_by(date(2026, 10, 19), 0) is None
	assert dates.lot_code(date(2026, 10, 19)) == "L261019"
	assert dates.lot_code(date(2026, 10, 19), 3) == "L261019-3"
	assert dates.next_lot(date(2026, 10, 19), []) == "L261019"
	assert dates.next_lot(date(2026, 10, 19), ["L261019", "L261019-2"]) == "L261019-3"


@pytest.mark.parametrize("use_by,state", [
	(datetime(2026, 10, 19, 9, 0), "past"),
	(datetime(2026, 10, 19, 18, 0), "today"),
	(datetime(2026, 10, 20, 8, 0), "soon"),
	(datetime(2026, 10, 25, 8, 0), "ok"),
	(date(2026, 10, 18), "past"),
	(date(2026, 10, 19), "today"),  # a date lasts until 23:59
	(date(2026, 10, 20), "soon"),
	(None, "ok"),
])
def test_date_state(use_by, state):
	assert dates.date_state(use_by, datetime(2026, 10, 19, 12, 0)) == state


def test_formats():
	assert dates.fmt_when(datetime(2026, 10, 19, 7, 5)) == "19/10 07:05"
	assert dates.fmt_when(date(2026, 10, 19)) == "19/10/26"
	assert dates.fmt_when(None) == ""


def test_opened_label_lines():
	lines = dl.kitchen_lines({
		"kind": "Opened", "item_name": "Unsalted butter", "item_name_zh": "無鹽牛油",
		"start": datetime(2026, 10, 19, 14, 30), "use_by": datetime(2026, 10, 21, 23, 59),
		"storage": "Chilled", "allergens": [("Milk", "奶")], "by": "Ana", "lot": "L261015",
	})
	assert lines == [
		("title", "Unsalted butter"),
		("sub", "無鹽牛油"),
		("row", "OPENED 開封  19/10 14:30"),
		("big", "USE BY 此前使用  21/10 23:59"),
		("row", "Chilled 冷藏"),
		("small", "Contains 含: Milk 奶"),
		("small", "Batch 批次 L261015  ·  By 經手 Ana"),
	]


def test_batch_label_lines_skip_what_is_missing():
	lines = dl.kitchen_lines({
		"kind": "Batch", "item_name": "Cookie dough", "item_name_zh": "Cookie dough",
		"start": date(2026, 10, 19), "use_by": None, "lot": "L261019-2",
	})
	assert lines == [
		("title", "Cookie dough"),
		("row", "BATCH 批次  L261019-2"),
		("row", "MADE 製造  19/10/26"),
		("big", "USE BY 此前使用  -"),
	]


def test_small_label_draws_within_the_roll():
	pytest.importorskip("PIL")
	from happy_kitchen.hk_operations import label_render as lr

	lines = dl.kitchen_lines({
		"kind": "Opened", "item_name": "A very long ingredient name that has to wrap onto a second line " * 2,
		"start": datetime(2026, 10, 19, 14, 30), "use_by": datetime(2026, 10, 19, 18, 30),
		"storage": "Ambient", "allergens": [("Gluten", "麩質"), ("Eggs", "蛋"), ("Milk", "奶")], "by": "Ana",
	})
	img = lr.render_kitchen(lines, 50, 30, 203)
	assert img.size == (400, 240)  # 50 x 30 mm at 203 dpi, landscape
	assert img.getbbox() is not None  # something was drawn
	zpl = lr.to_zpl(lr.for_printer(img, 50, 30), 3)
	assert zpl.startswith("^XA") and "^PQ3" in zpl
