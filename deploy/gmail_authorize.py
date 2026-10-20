#!/usr/bin/env python3
"""One-time Google sign-in for the Gmail order pick-up. Run it on YOUR OWN computer, not the server.

    python3 deploy/gmail_authorize.py

It asks for the Google client ID and secret (the secret is typed hidden), opens your browser to
sign in with the Gmail account that receives the orders, and prints a refresh token in this
terminal only. Paste the three values into Gmail Settings on the site. Nothing is written to disk.
Scope: gmail.readonly (the token can read mail; it cannot send, label or delete). Standard library only."""

import base64
import getpass
import hashlib
import http.server
import json
import secrets
import threading
import urllib.parse
import urllib.request
import webbrowser

SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"


def main():
	client_id = input("Google client ID: ").strip()
	client_secret = getpass.getpass("Google client secret (hidden): ").strip()
	verifier = secrets.token_urlsafe(64)
	challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
	state = secrets.token_urlsafe(16)
	result = {}

	class Handler(http.server.BaseHTTPRequestHandler):
		def do_GET(self):
			q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
			result["code"], result["state"], result["error"] = (q.get(k, [""])[0] for k in ("code", "state", "error"))
			self.send_response(200)
			self.send_header("Content-Type", "text/plain; charset=utf-8")
			self.end_headers()
			self.wfile.write(b"Done. You can close this tab and go back to the terminal.")
			threading.Thread(target=self.server.shutdown, daemon=True).start()

		def log_message(self, *a):
			pass

	server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
	redirect = f"http://127.0.0.1:{server.server_port}"
	url = AUTH_URL + "?" + urllib.parse.urlencode({
		"client_id": client_id, "redirect_uri": redirect, "response_type": "code", "scope": SCOPE,
		"access_type": "offline", "prompt": "consent", "state": state,
		"code_challenge": challenge, "code_challenge_method": "S256"})
	print("\nOpening your browser. Sign in with the Gmail account that receives the orders.")
	print("If it does not open, paste this address into your browser:\n" + url + "\n")
	webbrowser.open(url)
	server.serve_forever()
	if result.get("error") or result.get("state") != state or not result.get("code"):
		raise SystemExit(f"Sign-in failed: {result.get('error') or 'unexpected reply'}")

	data = urllib.parse.urlencode({
		"code": result["code"], "client_id": client_id, "client_secret": client_secret, "redirect_uri": redirect,
		"grant_type": "authorization_code", "code_verifier": verifier}).encode()
	with urllib.request.urlopen(urllib.request.Request(TOKEN_URL, data=data), timeout=30) as r:
		token = json.load(r)
	if not token.get("refresh_token"):
		raise SystemExit("Google did not return a refresh token. Remove the app's access at "
		                 "https://myaccount.google.com/permissions and run this again.")
	print("Granted scope:", token.get("scope"))
	print("\nGoogle refresh token (paste into Gmail Settings; treat it like a password):\n")
	print(token["refresh_token"])


if __name__ == "__main__":
	main()
