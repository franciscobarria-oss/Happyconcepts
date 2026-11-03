"""Kitchen Checks starting data (patch compliance_setup). Plain data, tested in
tests/test_compliance_setup.py. Everything is a starting point the team edits; schedules are
created switched off, so no checklist is due until a manager ticks Active."""

AREA = ("Central Kitchen", "中央廚房", "Central Kitchen")  # (name, Chinese, department without " - HK")

Y = "Yes/No"

TEMPLATES = [
	{
		"title": "Opening checks", "title_zh": "開店檢查", "category": "Opening", "requires_review": 0,
		"schedule": ("Daily", "06:30", "07:30"),
		"items": [
			{"prompt": "Hand-wash basins have soap, paper towels and hot water", "prompt_zh": "洗手盆有梘液、抹手紙及熱水", "answer_type": Y},
			{"prompt": "Sanitiser made up at the right strength", "prompt_zh": "消毒液濃度正確", "answer_type": Y, "critical": 1},
			{"prompt": "Walk-in chiller temperature", "prompt_zh": "凍房溫度", "answer_type": "Number", "max_value": "5", "unit": "°C", "critical": 1},
			{"prompt": "Freezer temperature", "prompt_zh": "冰櫃溫度", "answer_type": "Number", "max_value": "-18", "unit": "°C", "critical": 1},
			{"prompt": "Work surfaces clean and sanitised", "prompt_zh": "工作枱已清潔消毒", "answer_type": Y},
			{"prompt": "No signs of pests", "prompt_zh": "沒有蟲鼠跡象", "answer_type": Y, "critical": 1},
			{"prompt": "Staff fit for work and in clean uniform", "prompt_zh": "員工身體狀況良好及制服整潔", "answer_type": Y},
		],
	},
	{
		"title": "Closing checks", "title_zh": "收舖檢查", "category": "Closing", "requires_review": 1,
		"schedule": ("Daily", "20:00", "22:00"),
		"items": [
			{"prompt": "Food covered, labelled and dated", "prompt_zh": "食物已蓋好及貼上日期標籤", "answer_type": Y, "critical": 1},
			{"prompt": "Out-of-date or opened-too-long food thrown away", "prompt_zh": "過期食物已棄置", "answer_type": Y},
			{"prompt": "Walk-in chiller temperature", "prompt_zh": "凍房溫度", "answer_type": "Number", "max_value": "5", "unit": "°C", "critical": 1},
			{"prompt": "Floors swept and mopped", "prompt_zh": "地面已掃及拖", "answer_type": Y},
			{"prompt": "Bins emptied and cleaned", "prompt_zh": "垃圾桶已清倒及清洗", "answer_type": Y},
			{"prompt": "Gas, ovens and equipment switched off", "prompt_zh": "煤氣、焗爐及設備已關", "answer_type": Y, "critical": 1},
			{"prompt": "Photo of the kitchen at close", "prompt_zh": "收舖時廚房相片", "answer_type": "Photo", "required": 0},
		],
	},
	{
		"title": "Daily cleaning", "title_zh": "每日清潔", "category": "Cleaning", "requires_review": 0,
		"schedule": ("Daily", "14:00", "16:00"),
		"items": [
			{"prompt": "Mixers and slicers cleaned", "prompt_zh": "攪拌機及切片機已清潔", "answer_type": Y},
			{"prompt": "Chiller handles and door seals wiped", "prompt_zh": "雪櫃手柄及門膠已抹", "answer_type": Y},
			{"prompt": "Dish-wash area", "prompt_zh": "洗碗區", "answer_type": "Choice", "choices": "Clean\nNeeds attention",
			 "fail_choices": "Needs attention"},
			{"prompt": "Notes", "prompt_zh": "備註", "answer_type": "Text", "required": 0},
		],
	},
]

PRESETS = [
	("Cleaned and sanitised again", "已重新清潔消毒", ""),
	("Made up fresh sanitiser and re-tested", "已重新調配消毒液並再測試", "Opening"),
	("Moved food to another chiller and told the manager", "已將食物移往其他雪櫃並通知經理", ""),
	("Checked again after 30 minutes", "30分鐘後再檢查", ""),
	("Food thrown away and logged as wastage", "食物已棄置並記錄損耗", ""),
	("Refilled soap / paper towels", "已補充梘液／抹手紙", ""),
	("Reported to the manager", "已通知經理", ""),
]
