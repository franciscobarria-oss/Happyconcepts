"""Kitchen Checks: is an answer a pass or a fail, and can the checklist be signed.
Pure Python (tests/test_compliance_scoring.py). An item / answer is a plain dict with the
Checklist Run Answer fields."""

from __future__ import annotations

ANSWER_TYPES = ("Yes/No", "Number", "Text", "Choice", "Photo")
PASS, FAIL = "Pass", "Fail"


def _lines(text) -> list[str]:
	return [s.strip() for s in str(text or "").splitlines() if s.strip()]


def _num(value):
	if value is None or str(value).strip() == "":
		return None
	try:
		return float(str(value).strip().replace(",", "."))
	except (TypeError, ValueError):
		return None


def has_value(row: dict) -> bool:
	if row.get("answer_type") == "Photo":
		return bool(row.get("photo"))
	return str(row.get("value") or "").strip() != ""


def limits(row: dict) -> tuple:
	"""(lowest, highest) allowed as floats or None. The fields are text so that blank means
	"no limit" (a Float field would store 0, and 0 °C is a real limit)."""
	return _num(row.get("min_value")), _num(row.get("max_value"))


def limits_text(row: dict) -> str:
	"""'0 – 5 °C', '≥ 75 °C', '≤ 5', or '' (no limits)."""
	lo, hi = limits(row)
	unit = (row.get("unit") or "").strip()
	if lo is not None and hi is not None:
		s = f"{lo:g} – {hi:g}"
	elif lo is not None:
		s = f"≥ {lo:g}"
	elif hi is not None:
		s = f"≤ {hi:g}"
	else:
		return ""
	return f"{s} {unit}".strip()


def bad_limits(row: dict) -> bool:
	"""A limit that is filled in but not a number, or lowest above highest."""
	lo, hi = limits(row)
	for raw, n in ((row.get("min_value"), lo), (row.get("max_value"), hi)):
		if str(raw or "").strip() and n is None:
			return True
	return lo is not None and hi is not None and lo > hi


def evaluate(row: dict) -> str:
	"""'Pass', 'Fail', or '' (not answered / nothing to judge)."""
	if not has_value(row):
		return ""
	kind, value = row.get("answer_type"), str(row.get("value") or "").strip()
	if kind == "Yes/No":
		expected = row.get("expected") or "Yes"
		return PASS if value == expected else FAIL
	if kind == "Number":
		n = _num(value)
		if n is None:
			return FAIL
		lo, hi = limits(row)
		if lo is not None and n < lo:
			return FAIL
		if hi is not None and n > hi:
			return FAIL
		return PASS
	if kind == "Choice":
		return FAIL if value in _lines(row.get("fail_choices")) else PASS
	return PASS  # Text, Photo: answered is enough


PROBLEMS = ("unanswered", "not_number", "bad_choice", "photo", "corrective")


def problems(rows: list[dict]) -> list[tuple[int, str, str]]:
	"""Why the checklist can't be signed yet, as (row number from 1, prompt, code); empty = it can.
	Codes are PROBLEMS; the API turns them into translated messages."""
	out = []
	for i, r in enumerate(rows, start=1):
		label = r.get("prompt") or f"#{i}"
		if r.get("required", 1) and not has_value(r):
			out.append((i, label, "unanswered"))
			continue
		if r.get("answer_type") == "Number" and has_value(r) and _num(r.get("value")) is None:
			out.append((i, label, "not_number"))
		if r.get("answer_type") == "Choice" and has_value(r) and _lines(r.get("choices")) \
				and str(r.get("value")).strip() not in _lines(r.get("choices")):
			out.append((i, label, "bad_choice"))
		if r.get("photo_required") and r.get("answer_type") != "Photo" and not r.get("photo"):
			out.append((i, label, "photo"))
		if evaluate(r) == FAIL and not str(r.get("corrective_action") or "").strip():
			out.append((i, label, "corrective"))
	return out


def outcome(rows: list[dict]) -> tuple[str, int, int]:
	"""(status, issues, critical issues) once signed: 'Completed' or 'Completed with issues'."""
	fails = [r for r in rows if evaluate(r) == FAIL]
	critical = sum(1 for r in fails if r.get("critical"))
	return ("Completed with issues" if fails else "Completed"), len(fails), critical


COPY_FIELDS = ("prompt", "prompt_zh", "answer_type", "expected", "min_value", "max_value", "unit", "choices",
               "fail_choices", "photo_required", "required", "critical", "help")


def answers_from_template(items: list[dict]) -> list[dict]:
	"""Each run keeps its own copy of the prompts and limits, so editing a template never changes history."""
	return [{k: it.get(k) for k in COPY_FIELDS} for it in items]
