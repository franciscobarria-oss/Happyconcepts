from datetime import date, datetime

from happy_kitchen.hk_operations import continuous as c


def dt(d, h, m=0):
	return datetime(2026, 10, d, h, m)


def test_shift_hours_pairs_in_out():
	rows = [("IN", dt(7, 7, 30)), ("OUT", dt(7, 16, 30)), ("IN", dt(8, 7, 30)), ("OUT", dt(8, 10, 0)), ("IN", dt(9, 7, 30))]
	assert c.shift_hours(rows) == {date(2026, 10, 7): 9.0, date(2026, 10, 8): 2.5}


def test_window_is_28_days_inclusive():
	days = {date(2026, 10, 3): 10.0, date(2026, 10, 30): 5.0}
	assert c.window_hours(days, date(2026, 10, 30)) == 15.0
	assert c.window_hours(days, date(2026, 10, 31)) == 5.0


def test_levels():
	assert c.level(54.3) == c.BELOW
	assert c.level(54.4) == c.CLOSE
	assert c.level(67.99) == c.CLOSE
	assert c.level(68) == c.REACHED


def test_worsened_only_goes_up():
	assert c.worsened(None, c.CLOSE) and c.worsened(c.CLOSE, c.REACHED)
	assert not c.worsened(c.REACHED, c.REACHED) and not c.worsened(c.REACHED, c.CLOSE)
	assert not c.worsened(None, c.BELOW)


def test_october_sheet_examples():
	assert c.level(132) == c.REACHED and c.level(114) == c.REACHED
	assert c.level(26) == c.BELOW
	assert "4 weeks" in c.message("Taka", 70, c.REACHED)
