#!/usr/bin/env python3
"""Happy Kitchen label agent for a Raspberry Pi with a USB label printer.

Every few seconds it asks the ERP for the next label job, sends it to the
printer and reports back. It only makes outgoing HTTPS requests, so nothing on
the router needs to change. Standard library only (Python 3.9+).

Settings: /etc/hk-label-agent.conf (see install.sh). Run by systemd as
hk-label-agent.service; logs: journalctl -u hk-label-agent -f

  hk_label_agent.py              run forever
  hk_label_agent.py --selftest   print a one-line test label without the ERP
  hk_label_agent.py --once       ask the ERP once and exit (for testing)
"""

import base64
import configparser
import json
import logging
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

VERSION = "1.0"
CONFIG = os.environ.get("HK_LABEL_CONFIG", "/etc/hk-label-agent.conf")
log = logging.getLogger("hk-label-agent")


def load_config(path=CONFIG):
	cp = configparser.ConfigParser()
	if not cp.read(path):
		sys.exit(f"Settings file {path} not found. Run install.sh first.")
	c = {
		"url": cp.get("erp", "url").rstrip("/"),
		"api_key": cp.get("erp", "api_key", fallback=""),
		"api_secret": cp.get("erp", "api_secret", fallback=""),
		"printer": cp.get("erp", "printer"),
		"device": cp.get("output", "device", fallback="").strip(),
		"cups": cp.get("output", "cups_queue", fallback="").strip(),
		"poll": max(2, cp.getint("output", "poll_seconds", fallback=3)),
	}
	if not c["api_key"] or not c["api_secret"]:
		sys.exit(f"api_key / api_secret are empty in {path}.")
	if not (c["device"] or c["cups"]):
		sys.exit(f"Set either device or cups_queue in {path}.")
	return c


def call(c, method, **data):
	req = urllib.request.Request(
		f"{c['url']}/api/method/happy_kitchen.hk_operations.labels.{method}",
		data=urllib.parse.urlencode(data).encode(),
		headers={"Authorization": f"token {c['api_key']}:{c['api_secret']}", "Accept": "application/json"},
		method="POST",
	)
	with urllib.request.urlopen(req, timeout=30) as r:
		return json.loads(r.read().decode() or "{}").get("message")


def printer_problem(c):
	"""Why we can't print right now, or None."""
	if c["device"]:
		if not os.path.exists(c["device"]):
			return f"printer not found at {c['device']} (unplugged or switched off?)"
		if not os.access(c["device"], os.W_OK):
			return f"no permission to write to {c['device']}"
		return None
	try:
		out = subprocess.run(["lpstat", "-p", c["cups"]], capture_output=True, text=True, timeout=10)
	except FileNotFoundError:
		return "CUPS is not installed (sudo apt install cups)"
	if out.returncode != 0:
		return f"CUPS printer {c['cups']} not found"
	if "disabled" in out.stdout:
		return f"CUPS printer {c['cups']} is paused"
	return None


def send_raw(c, data: bytes):
	if c["device"]:
		with open(c["device"], "wb") as f:
			f.write(data)
			f.flush()
		return
	subprocess.run(["lp", "-d", c["cups"], "-o", "raw"], input=data, check=True, capture_output=True, timeout=120)


def send_png(c, png: bytes, copies: int):
	if not c["cups"]:
		raise RuntimeError("This printer is set to PNG in the ERP, which needs cups_queue in the Pi's settings.")
	with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
		f.write(png)
		path = f.name
	try:
		subprocess.run(["lp", "-d", c["cups"], "-n", str(copies), "-o", "fit-to-page", path],
		               check=True, capture_output=True, timeout=120)
	finally:
		os.unlink(path)


def print_job(c, job):
	for label in job["labels"]:
		if "zpl" in label:
			send_raw(c, label["zpl"].encode("utf-8"))
		else:
			send_png(c, base64.b64decode(label["png"]), int(label.get("copies") or 1))


def poll_once(c):
	problem = printer_problem(c)
	job = call(c, "agent_poll", printer=c["printer"], agent_version=VERSION,
	           host=socket.gethostname(), ready=0 if problem else 1, problem=problem or "")
	if problem:
		log.warning(problem)
		return False
	if not job or not job.get("job"):
		return False
	log.info("printing %s (%s labels)", job["job"], job.get("count"))
	try:
		print_job(c, job)
	except Exception as e:  # report every printer error back to the ERP
		log.error("%s failed: %s", job["job"], e)
		call(c, "agent_done", printer=c["printer"], job=job["job"], ok=0, error=str(e)[:900])
		return True
	call(c, "agent_done", printer=c["printer"], job=job["job"], ok=1)
	return True


def selftest(c):
	zpl = ("^XA^CI28^FO40,60^A0N,48,48^FDHK label test^FS"
	       f"^FO40,130^A0N,32,32^FDPi label test {time.strftime('%Y-%m-%d %H:%M')}^FS^XZ\n")
	problem = printer_problem(c)
	if problem:
		sys.exit(problem)
	send_raw(c, zpl.encode())
	print("Sent a test label.")


def main():
	logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
	c = load_config()
	if "--selftest" in sys.argv:
		return selftest(c)
	if "--once" in sys.argv:
		print("printed a job" if poll_once(c) else "nothing printed")
		return
	log.info("agent %s for printer '%s' at %s", VERSION, c["printer"], c["url"])
	wait = c["poll"]
	while True:
		try:
			busy = poll_once(c)
			wait = 0 if busy else c["poll"]  # straight on to the next job when busy
		except urllib.error.HTTPError as e:
			body = e.read().decode(errors="replace")[:300]
			log.error("ERP answered %s: %s", e.code, body)
			wait = 60 if e.code in (401, 403) else 15
		except Exception as e:  # network down, ERP restarting...
			log.error("can't reach the ERP: %s", e)
			wait = min(max(wait * 2, 5), 60)
		time.sleep(wait)


if __name__ == "__main__":
	main()
