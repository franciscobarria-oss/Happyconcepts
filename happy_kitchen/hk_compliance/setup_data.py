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


# Food safety checklists from the HCF food safety task list (FS-D / FS-W / FS-M, Francisco 2026-11-17).
# Patch food_safety_checklists. Schedules are switched off; times and days are starting points a
# manager changes before ticking Active. Six-monthly, yearly and ad hoc tasks stay ERPNext Tasks.
CHILLER = {"answer_type": "Number", "min_value": "0", "max_value": "4", "unit": "°C", "critical": 1}
FREEZER = {"answer_type": "Number", "max_value": "-18", "unit": "°C", "critical": 1}


def _temps(check: str) -> list[dict]:
	return [
		{"prompt": "Freezer temperature (-18 °C or colder)", "prompt_zh": "冰櫃溫度（-18 °C 或以下）", **FREEZER,
		 "help": f"{check} · FM-ST-01 · CCP · NSF CAR 18. Out of range: move food to the M1 cold room, discard spoiled food."},
		{"prompt": "Chiller temperature (0–4 °C)", "prompt_zh": "雪櫃溫度（0–4 °C）", **CHILLER,
		 "help": f"{check} · FM-ST-01 · CCP · NSF CAR 18. Out of range: move food to the M1 cold room, discard spoiled food."},
	]


FOOD_SAFETY = [
	{
		"title": "Before production checks", "title_zh": "生產前檢查", "category": "Food safety", "requires_review": 0,
		"schedule": {"frequency": "Daily", "start_time": "07:00", "due_time": "08:30"},
		"items": [
			{"prompt": "Staff hygiene and uniform: hairnet, clean uniform, no jewellery or watches, short clean nails",
			 "prompt_zh": "員工衞生及制服：髮網、制服整潔、不戴首飾或手錶、指甲短而清潔", "answer_type": Y,
			 "help": "FS-D-01 · FM-HY-01, WI-HY-04 · NSF CAR 22. Random checks during the day too."},
			{"prompt": "Scale tested with a known weight and passed", "prompt_zh": "已用標準砝碼測試磅並合格", "answer_type": Y,
			 "critical": 1, "help": "FS-D-02 · FM-QC-01 · NSF CAR 19. A failed scale is taken out of use."},
			{"prompt": "Equipment OK: no rust, peeling paint, damaged trays or wooden-handled tools",
			 "prompt_zh": "設備正常：沒有生鏽、甩漆、損壞托盤或木柄工具", "answer_type": Y, "help": "FS-D-03 · NSF CAR 10, 16"},
			*_temps("FS-D-04 (check 1 of 3)"),
			{"prompt": "Fridges segregated: raw apart from finished product; hold area only has labelled HOLD items",
			 "prompt_zh": "雪櫃分隔：生料與製成品分開；隔離區只放已標示 HOLD 的物品", "answer_type": Y,
			 "help": "FS-D-05 · NSF CAR 7, 11"},
			{"prompt": "Packing area (frozen dough): bench, scale, trays and tools cleaned and sanitised; no raw meat or poultry nearby",
			 "prompt_zh": "包裝區（急凍麵糰）：工作枱、磅、托盤及工具已清潔消毒；附近沒有處理生肉或家禽",
			 "answer_type": Y, "help": "FS-D-06 · SOP-FD-PKG-01"},
		],
	},
	{
		"title": "During production records", "title_zh": "生產期間記錄", "category": "Food safety", "requires_review": 1,
		"schedule": {"frequency": "Daily", "start_time": "08:30", "due_time": "17:00"},
		"items": [
			{"prompt": "Every delivery checked: chilled 4 °C or colder, frozen -18 °C or colder, packaging intact, in date",
			 "prompt_zh": "每批送貨已檢查：冷藏 4 °C 或以下、急凍 -18 °C 或以下、包裝完好、未過期", "answer_type": Y,
			 "critical": 1, "help": "FS-D-07 · FM-RM-01 · CCP 1. Reject or HOLD if not."},
			{"prompt": "Lot code, expiry and quantity received recorded; date received labelled; stored off floor and wall (FIFO / FEFO)",
			 "prompt_zh": "已記錄批號、到期日及收貨數量；已貼收貨日期；離地離牆存放（先進先出／先到期先出）",
			 "answer_type": Y, "help": "FS-D-08 · SOP-TR-01, WI-001 · NSF CAR 4"},
			{"prompt": "Batch record kept for every batch, verified by the supervisor before release",
			 "prompt_zh": "每批均有生產記錄，放行前經主管核實", "answer_type": Y,
			 "help": "FS-D-09 · FM-RM-03, SOP-TR-01 · NSF CAR 4"},
			{"prompt": "Cooking: core above 75 °C for 30 s, surface below 25 °C before packing, every batch",
			 "prompt_zh": "烹煮：每批中心溫度高於 75 °C 達 30 秒，包裝前表面低於 25 °C", "answer_type": Y,
			 "critical": 1, "help": "FS-D-10 · FM-PR-01, Hazard Control Plan · CCP"},
			{"prompt": "Product weight checked every run; under-weight product held and corrected or disposed",
			 "prompt_zh": "每次生產均檢查重量；重量不足的產品已暫扣並修正或棄置", "answer_type": Y,
			 "help": "FS-D-11 · FM-QC-02 · NSF CAR 20"},
			{"prompt": "Frozen dough packing: seal intact, lot/date and 'Bake before eating' label; nothing soft or thawed dispatched",
			 "prompt_zh": "急凍麵糰包裝：封口完好，標籤有批號／日期及「食用前須烘焗」；沒有發出變軟或解凍的產品",
			 "answer_type": Y, "critical": 1, "help": "FS-D-12 · SOP-FD-PKG-01, HACCP Frozen Dough plan · CCP"},
			{"prompt": "Opened items labelled with their shelf life (secondary shelf life table)",
			 "prompt_zh": "已開封物品已按次保質期表貼上標籤", "answer_type": Y, "help": "FS-D-13 · WI-ST-01"},
		],
	},
	{
		"title": "Noon temperature check", "title_zh": "中午溫度檢查", "category": "Temperature", "requires_review": 0,
		"schedule": {"frequency": "Daily", "start_time": "12:00", "due_time": "13:30"},
		"items": _temps("FS-D-14 (check 2 of 3)"),
	},
	{
		"title": "End of day checks", "title_zh": "收工檢查", "category": "Food safety", "requires_review": 1,
		"schedule": {"frequency": "Daily", "start_time": "17:00", "due_time": "19:00"},
		"items": [
			*_temps("FS-D-15 (check 3 of 3)"),
			{"prompt": "Zones A–E cleaned: shelves, floors, equipment, benches, sinks, bins, mixer, lockers",
			 "prompt_zh": "A–E 區已清潔：層架、地面、設備、工作枱、洗手盆、垃圾桶、攪拌機、儲物櫃",
			 "answer_type": Y, "help": "FS-D-16 · FM-CL-07"},
			{"prompt": "Drains: no standing water; any blockage reported", "prompt_zh": "坑渠：沒有積水；淤塞已即時報告",
			 "answer_type": Y, "help": "FS-D-17 · NSF CAR 13. Blockages fixed at once."},
			{"prompt": "Rubbish removed from production and packing areas; lidded, labelled bins (no cardboard boxes)",
			 "prompt_zh": "生產及包裝區垃圾已清走；使用有蓋及有標示的垃圾桶（不用紙箱）", "answer_type": Y,
			 "help": "FS-D-18 · WI-006"},
			{"prompt": "Today's logs reviewed: all three temperature checks done, scale log complete",
			 "prompt_zh": "已覆核今日記錄：三次溫度檢查已完成，磅記錄齊全", "answer_type": Y,
			 "help": "FS-D-19 · FM-ST-01, FM-QC-01 · NSF CAR 18"},
		],
	},
	{
		"title": "Drain cleaning", "title_zh": "清洗坑渠", "category": "Cleaning", "requires_review": 0,
		"schedule": {"frequency": "Selected weekdays", "weekdays": ("Wed", "Sat"), "start_time": "16:00", "due_time": "19:00"},
		"items": [
			{"prompt": "Drains cleaned", "prompt_zh": "坑渠已清洗", "answer_type": Y, "help": "FS-W-01 · FM-CL-07"},
		],
	},
	{
		"title": "Weekly air-conditioner cleaning", "title_zh": "每週冷氣清潔", "category": "Cleaning", "requires_review": 0,
		"schedule": {"frequency": "Selected weekdays", "weekdays": ("Sat",), "start_time": "14:00", "due_time": "19:00"},
		"items": [
			{"prompt": "Air-conditioner filters, covers and outlets cleaned", "prompt_zh": "冷氣隔塵網、外殼及出風口已清潔",
			 "answer_type": Y, "help": "FS-W-02 · FM-CL-07 · NSF CAR 9"},
		],
	},
	{
		"title": "Weekly temperature log review", "title_zh": "每週溫度記錄覆核", "category": "Temperature", "requires_review": 1,
		"schedule": {"frequency": "Selected weekdays", "weekdays": ("Mon",), "start_time": "09:00", "due_time": "18:00"},
		"items": [
			{"prompt": "Last week's temperature checks all completed and signed", "prompt_zh": "上週溫度檢查全部完成及已簽署",
			 "answer_type": Y, "help": "FS-W-03 · FM-ST-01 · NSF CAR 18"},
			{"prompt": "Every out-of-range reading has a corrective action", "prompt_zh": "所有超出範圍的讀數均有糾正措施",
			 "answer_type": Y, "critical": 1, "help": "FS-W-03 · FM-ST-01 · NSF CAR 18"},
		],
	},
	{
		"title": "Monthly food safety inspection", "title_zh": "每月食物安全巡查", "category": "Food safety", "requires_review": 1,
		"schedule": {"frequency": "Monthly", "day_of_month": 15, "start_time": "09:00", "due_time": "18:00"},
		"items": [
			{"prompt": "Glass, brittle plastic, metal and equipment inspected; nothing damaged",
			 "prompt_zh": "已巡查玻璃、易碎塑膠、金屬及設備；沒有損壞", "answer_type": Y, "critical": 1,
			 "help": "FS-M-01 · FM-MS-01 · NSF CAR 17. Light covers, doors, windows, guards, clock, gauges, film, utensils, fridge, freezer. Damage = stop production."},
			{"prompt": "No wooden, damaged or unsuitable tools in product areas", "prompt_zh": "產品區沒有木製、損壞或不合適的工具",
			 "answer_type": Y, "help": "FS-M-02 · NSF CAR 16"},
			{"prompt": "Equipment condition reviewed; damaged items tagged and not used",
			 "prompt_zh": "已檢查設備狀況；損壞物品已標示並停用", "answer_type": Y,
			 "help": "FS-M-03 · FM-MT-01 · NSF CAR 10. Electrical, plumbing, CCTV, aircon, stoves, cold room, ventilation, oven, mixers."},
			{"prompt": "Ventilation and aircon units cleaned this month", "prompt_zh": "本月已清潔通風及冷氣機",
			 "answer_type": Y, "help": "FS-M-04 · Ventilation Cleaning Record · NSF CAR 9"},
			{"prompt": "Pest trend reviewed after the LBS visit; repeat activity investigated",
			 "prompt_zh": "LBS 到訪後已覆核蟲鼠趨勢；重複出現已調查", "answer_type": Y,
			 "help": "FS-M-05 · FM-PC-02, LBS reports · NSF CAR 15"},
			{"prompt": "Internal hygiene inspection: non-conformities found", "prompt_zh": "內部衞生巡查：不合格項目數目",
			 "answer_type": "Number", "max_value": "2", "help": "FS-M-06 · Objective analysis report · NSF CAR 3. Target fewer than 3."},
			{"prompt": "Food safety meeting with staff held; minutes kept", "prompt_zh": "已與員工舉行食物安全會議並保存會議記錄",
			 "answer_type": Y, "help": "FS-M-08 · NSF CAR 3"},
		],
	},
	{
		"title": "Month-end food safety sign-off", "title_zh": "月底食物安全簽核", "category": "Food safety", "requires_review": 1,
		"schedule": {"frequency": "Monthly", "day_of_month": 31, "start_time": "09:00", "due_time": "18:00"},
		"items": [
			{"prompt": "Food safety objectives report done: non-conformities, out-of-CCP cases, complaints",
			 "prompt_zh": "已完成食物安全目標報告：不合格項目、偏離關鍵控制點個案、投訴", "answer_type": Y,
			 "help": "FS-M-07 · Objective analysis report"},
			{"prompt": "Month's forms signed by the supervisor and QA manager (FM-CL-07, FM-ST-01, FM-MT-01)",
			 "prompt_zh": "本月表格已由主管及品質經理簽署（FM-CL-07、FM-ST-01、FM-MT-01）", "answer_type": Y,
			 "help": "FS-M-09 · Form footers"},
		],
	},
]
