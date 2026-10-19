import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from happy_kitchen.hk_operations import calc  # noqa: E402


def test_own_wage_monthly():
	assert calc.own_hourly_wage(20000, 24, 9) == pytest.approx(92.5926, abs=1e-4)


def test_own_wage_prefers_hourly_rate():
	assert calc.own_hourly_wage(20000, 24, 9, hourly_rate=65) == 65


def test_own_wage_missing_fields():
	assert calc.own_hourly_wage(20000, 0, 9) == 0
	assert calc.own_hourly_wage(0, 24, 9) == 0


def test_fixed_rate():
	assert calc.overtime_amount(3.5, calc.overtime_hourly_amount(calc.FIXED, 80)) == 280.00


def test_time_and_a_half_matches_spec():
	wage = calc.own_hourly_wage(20000, 24, 9)
	hourly = calc.overtime_hourly_amount(calc.MULTIPLE, 1.5, wage)
	assert calc.overtime_amount(3.5, hourly) == 486.11


def test_unknown_method():
	with pytest.raises(ValueError):
		calc.overtime_hourly_amount("Per minute", 1)


def test_pct_change():
	assert calc.pct_change(495, 480) == pytest.approx(3.125)
	assert calc.pct_change(495, 0) is None
	assert calc.pct_change(0, 480) is None


@pytest.mark.parametrize(
	"cost,price,target,missing,tone",
	[
		(10, 40, 30, 0, "success"),  # 25%
		(12.4, 40, 30, 0, "warning"),  # 31%
		(16, 40, 30, 0, "danger"),  # 40%
		(10, 0, 30, 0, "warning"),  # no price
		(10, 40, 30, 2, "warning"),  # missing ingredient prices wins
		(10, 40, 0, 0, ""),  # no target set
	],
)
def test_food_cost_check(cost, price, target, missing, tone):
	assert calc.food_cost_check(cost, price, target, missing)[2] == tone


def test_food_cost_pct_value():
	pct, code, _ = calc.food_cost_check(10, 40, 30)
	assert pct == pytest.approx(25.0)
	assert code == "on_target"
	assert calc.food_cost_check(16, 40, 30)[1] == "over"
	assert calc.food_cost_check(10, 40, 30, missing_prices=2)[1] == "missing_prices"
