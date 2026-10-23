"""Every Custom HTML Block listed in setup/blocks.py has its files in happy_kitchen/blocks/."""

import ast
from pathlib import Path

from happy_kitchen.setup import block_files

APP = Path(__file__).resolve().parent.parent / "happy_kitchen"


def listed_blocks() -> dict:
	tree = ast.parse((APP / "setup" / "blocks.py").read_text(encoding="utf-8"))
	for node in tree.body:
		if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "BLOCKS" for t in node.targets):
			return ast.literal_eval(node.value)
	raise AssertionError("BLOCKS not found")


def test_every_block_has_html_and_script():
	blocks = listed_blocks()
	assert blocks, "no blocks listed"
	for name, stem in blocks.items():
		values = block_files.read_block(stem)
		assert values["html"].strip(), f"{name}: empty html"
		assert values["script"].strip(), f"{name}: empty script"
		assert "root_element" in values["script"], f"{name}: block scripts run in a shadow root"


def test_block_scripts_parse():
	"""A syntax error stops the whole block, so the page stays empty. Checked with node when present (CI has it)."""
	import shutil
	import subprocess

	import pytest

	node = shutil.which("node")
	if not node:
		pytest.skip("node is not installed")
	for name, stem in listed_blocks().items():
		script = block_files.read_block(stem)["script"]
		r = subprocess.run([node, "--check", "--input-type=commonjs", "-"], input=script, capture_output=True, text=True)
		assert r.returncode == 0, f"{name}: {r.stderr.strip()}"
