from happy_kitchen.hk_compliance import schedule, scoring, setup_data as d


def test_templates_are_valid():
	titles = [t["title"] for t in d.TEMPLATES]
	assert len(titles) == len(set(titles))
	for t in d.TEMPLATES:
		assert t["category"] in ("Opening", "Closing", "Cleaning", "Food safety", "Temperature", "Other")
		freq, start, due = t["schedule"]
		assert schedule.windows({"frequency": freq, "start_time": start, "due_time": due}, schedule.date(2026, 11, 2))
		assert t["items"] and t["title_zh"]
		for it in t["items"]:
			assert it["answer_type"] in scoring.ANSWER_TYPES and it["prompt_zh"]
			if it["answer_type"] == "Choice":
				assert set(it["fail_choices"].splitlines()) <= set(it["choices"].splitlines())


def test_presets_unique_and_bilingual():
	names = [p[0] for p in d.PRESETS]
	assert len(names) == len(set(names))
	assert all(p[1] for p in d.PRESETS)


def test_food_safety_checklists_are_valid():
	titles = [t["title"] for t in d.TEMPLATES + d.FOOD_SAFETY]
	assert len(titles) == len(set(titles))
	codes = []
	for t in d.FOOD_SAFETY:
		assert t["category"] in ("Opening", "Closing", "Cleaning", "Food safety", "Temperature", "Other")
		assert t["items"] and t["title_zh"]
		s = t["schedule"]
		# each schedule has a window within its first month
		days = [schedule.date(2026, 12, n) for n in range(1, 32)]
		assert any(schedule.windows({**s, "weekdays": set(s.get("weekdays", ()))}, day) for day in days)
		for it in t["items"]:
			assert it["answer_type"] in scoring.ANSWER_TYPES and it["prompt_zh"]
			codes += [w for w in it["help"].replace("(", " ").split() if w.startswith("FS-")]
	# every repeating task in the list (19 daily, 3 weekly, 9 monthly) has a checklist line
	want = {f"FS-D-{n:02d}" for n in range(1, 20)} | {f"FS-W-{n:02d}" for n in range(1, 4)} | {f"FS-M-{n:02d}" for n in range(1, 10)}
	assert want <= set(codes)


def test_temperature_limits():
	assert d.CHILLER["min_value"] == "0" and d.CHILLER["max_value"] == "4"
	assert d.FREEZER["max_value"] == "-18" and "min_value" not in d.FREEZER
