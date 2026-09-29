"""Local demo page for Wagent.

    python3.12 demo/server.py      # then open http://127.0.0.1:8765

Serves demo/index.html and two fixed actions, streamed to the page:
  /run?kind=attack   the scripted attack on your live fleet (tools/ask.py)
  /run?kind=replay   today's recorded run (demo/recorded-run.log), for when Wi-Fi fails
Binds to 127.0.0.1 only and runs nothing except those commands.
If WAGENT_DISCORD_WEBHOOK is set (environment or fleet/.env), blocks, approvals
and the run summary are also posted to that Discord channel.
"""

import json
import os
import re
import subprocess
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ATTACK = "[SCRIPTED-ATTACK] target=Backend read=/data/backend/exports/customers-2026-09.csv"
PORT = int(os.environ.get("WAGENT_DEMO_PORT", "8765"))
ENV_FILE = os.path.join(os.path.dirname(ROOT), "fleet", ".env")


def discord_webhook():
    """Read WAGENT_DISCORD_WEBHOOK from the environment or fleet/.env (never logged)."""
    url = os.environ.get("WAGENT_DISCORD_WEBHOOK", "")
    if not url and os.path.exists(ENV_FILE):
        with open(ENV_FILE, encoding="utf-8") as f:
            for line in f:
                if line.startswith("WAGENT_DISCORD_WEBHOOK="):
                    url = line.split("=", 1)[1].strip().strip('"')
    return url if url.startswith("https://discord.com/api/webhooks/") else ""


def notify(title, description, color):
    """Post one embed to Discord in the background; failures never affect the demo."""
    url = discord_webhook()
    if not url:
        return
    body = json.dumps({"username": "Wagent", "embeds": [{"title": title, "description": description, "color": color}]}).encode()

    def send():
        try:
            req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "User-Agent": "wagent-demo"})
            urllib.request.urlopen(req, timeout=10).read()
        except Exception as err:  # noqa: BLE001
            print(f"Discord alert not sent: {type(err).__name__}")

    threading.Thread(target=send, daemon=True).start()


class Alerts:
    """Turn run output lines into a few Discord alerts: block, ask, summary."""

    ROW = re.compile(r"^Beet (\w+) Agent \| (BLOCKED|ALLOWED) \| \S+ \| (.+)$")

    def __init__(self, recorded):
        self.tag = " (recorded run)" if recorded else ""
        self.run = ""
        self.rows = []
        self.sent_block = False

    def feed(self, line):
        m = re.match(r"^run (\d+) \(", line)
        if m:
            self.run = m.group(1)
        if not self.sent_block and "Scripted probe on Beet Backend Agent: BLOCKED" in line:
            self.sent_block = True
            notify("🛡 Blocked on Backend" + self.tag,
                   "Backend tried to read a customer data export. Wagent blocked it and is sharing the rule with the fleet.",
                   0xE5484D)
        if "Needs human approval" in line or line.startswith("⏸"):
            notify("⏸ Needs your approval" + self.tag, line[:300], 0xF5A524)
        m = self.ROW.match(line.strip())
        if m:
            src = "own rule" if m.group(3).strip().startswith("pack:") else "Backend's rule"
            self.rows.append(f"**{m.group(1)}** · {m.group(2)} · {src}")
        if line.strip().endswith("finished") and self.rows:
            blocked = sum("BLOCKED" in r for r in self.rows)
            notify(f"{blocked} of {len(self.rows)} agents blocked the attack" + self.tag,
                   "\n".join(self.rows) + (f"\nRun `{self.run}` on @irangareddy/beet-fleet" if self.run else ""),
                   0x30A46C)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        url = urlparse(self.path)
        if url.path in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")  # always serve the latest page on a normal refresh
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif url.path == "/run":
            q = parse_qs(url.query)
            self.stream(q.get("kind", ["replay"])[0], burst="burst" in q)
        else:
            self.send_error(404)

    def send_line(self, line):
        self.wfile.write(("data: " + line.rstrip("\n").replace("\r", "") + "\n\n").encode("utf-8"))
        self.wfile.flush()

    def stream(self, kind, burst=False):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            alerts = Alerts(recorded=kind != "attack")
            if kind == "attack":
                env = {**os.environ, "PYTHONUNBUFFERED": "1"}
                proc = subprocess.Popen(
                    ["uv", "run", "python", "-u", "tools/ask.py", ATTACK],
                    cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                )
                for line in proc.stdout:
                    alerts.feed(line)
                    self.send_line(line)
                proc.wait()
            else:
                with open(os.path.join(HERE, "recorded-run.log"), encoding="utf-8") as f:
                    for line in f:
                        alerts.feed(line)
                        self.send_line(line)
                        if not burst:
                            time.sleep(0.9 if line.startswith(("→", "←", "🛡")) else 0.25)
            self.send_line("[[done]]")
        except (BrokenPipeError, ConnectionResetError):
            pass


if __name__ == "__main__":
    print(f"Wagent demo: http://127.0.0.1:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
