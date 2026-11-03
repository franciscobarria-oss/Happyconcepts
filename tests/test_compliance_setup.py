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
