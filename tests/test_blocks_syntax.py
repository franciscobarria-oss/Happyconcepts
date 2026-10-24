"""Every Custom HTML Block script must parse: one redeclared name blanks the whole page in the browser."""

import shutil
import subprocess
from pathlib import Path

import pytest

BLOCKS = sorted((Path(__file__).resolve().parent.parent / "happy_kitchen" / "blocks").glob("*.js"))


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
@pytest.mark.parametrize("path", BLOCKS, ids=lambda p: p.name)
def test_block_script_parses(path):
	r = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
	assert r.returncode == 0, r.stderr
