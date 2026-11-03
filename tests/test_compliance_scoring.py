from happy_kitchen.hk_compliance import scoring as sc


def row(**kw):
	base = {"prompt": "Q", "answer_type": "Yes/No", "required": 1}
	base.update(kw)
	return base


def test_yes_no():
	assert sc.evaluate(row(value="Yes")) == "Pass"
	assert sc.evaluate(row(value="No")) == "Fail"
	assert sc.evaluate(row(value="No", expected="No")) == "Pass"
	assert sc.evaluate(row()) == ""


def test_number_limits():
	r = row(answer_type="Number", min_value=0, max_value=5, unit="°C")
	assert sc.evaluate({**r, "value": "4.5"}) == "Pass"
	assert sc.evaluate({**r, "value": "5,1"}) == "Fail"
	assert sc.evaluate({**r, "value": "-1"}) == "Fail"
	assert sc.evaluate({**r, "value": "abc"}) == "Fail"
	assert sc.limits_text(r) == "0 – 5 °C"
	assert sc.limits_text(row(answer_type="Number", min_value=75, unit="°C")) == "≥ 75 °C"
	assert sc.limits_text(row(answer_type="Number", max_value=5)) == "≤ 5"
	assert sc.limits_text(row(answer_type="Number")) == ""
	assert sc.evaluate(row(answer_type="Number", value="99")) == "Pass"  # no limits


def test_choice_and_photo_and_text():
	r = row(answer_type="Choice", choices="Clean\nDirty", fail_choices="Dirty")
	assert sc.evaluate({**r, "value": "Clean"}) == "Pass"
	assert sc.evaluate({**r, "value": "Dirty"}) == "Fail"
	assert sc.evaluate(row(answer_type="Photo", photo="/private/files/x.jpg")) == "Pass"
	assert sc.evaluate(row(answer_type="Photo", value="x")) == ""  # a photo item needs the photo
	assert sc.evaluate(row(answer_type="Text", value="ok")) == "Pass"


def test_problems():
	rows = [
		row(prompt="Hand-wash stocked", value="Yes"),
		row(prompt="Sanitiser", value="No"),
		row(prompt="Chiller", answer_type="Number", max_value=5, value="x"),
		row(prompt="Bins", answer_type="Choice", choices="Empty\nFull", value="Half"),
		row(prompt="Floor", value="Yes", photo_required=1),
		row(prompt="Notes", answer_type="Text", required=0),
		row(prompt="Door seal"),
	]
	assert sc.problems(rows) == [
		(2, "Sanitiser", "corrective"),
		(3, "Chiller", "not_number"),
		(3, "Chiller", "corrective"),
		(4, "Bins", "bad_choice"),
		(5, "Floor", "photo"),
		(7, "Door seal", "unanswered"),
	]
	assert {p[2] for p in sc.problems(rows)} <= set(sc.PROBLEMS)
	rows[1]["corrective_action"] = "Re-made sanitiser"
	assert (2, "Sanitiser", "corrective") not in sc.problems(rows)


def test_outcome():
	ok = [row(value="Yes")]
	assert sc.outcome(ok) == ("Completed", 0, 0)
	bad = ok + [row(value="No", critical=1, corrective_action="x"), row(value="No", corrective_action="y")]
	assert sc.outcome(bad) == ("Completed with issues", 2, 1)


def test_answers_from_template_copies_limits_only():
	items = [{"prompt": "Chiller", "answer_type": "Number", "max_value": 5, "unit": "°C", "name": "abc", "idx": 1}]
	copied = sc.answers_from_template(items)
	assert copied[0]["prompt"] == "Chiller" and copied[0]["max_value"] == 5
	assert "name" not in copied[0] and "idx" not in copied[0]


def test_limits_are_text_so_blank_is_no_limit():
	# a freezer: only a highest limit; 0 must not become a lowest limit
	r = row(answer_type="Number", min_value="", max_value="-18", unit="°C")
	assert sc.evaluate({**r, "value": "-20"}) == "Pass"
	assert sc.evaluate({**r, "value": "-10"}) == "Fail"
	assert sc.limits_text(r) == "≤ -18 °C"
	assert sc.evaluate(row(answer_type="Number", min_value="0", max_value="5", value="-0.5")) == "Fail"
	assert not sc.bad_limits(r)
	assert sc.bad_limits(row(min_value="abc"))
	assert sc.bad_limits(row(min_value="6", max_value="5"))
