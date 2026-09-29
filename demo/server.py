"""Local demo page for Wagent.

    python3.12 demo/server.py      # then open http://127.0.0.1:8765

Serves demo/index.html and two fixed actions, streamed to the page:
  /run?kind=attack   the scripted attack on your live fleet (tools/ask.py)
  /run?kind=replay   today's recorded run (demo/recorded-run.log), for when Wi-Fi fails
Binds to 127.0.0.1 only and runs nothing except those commands.
"""

import os
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ATTACK = "[SCRIPTED-ATTACK] target=Backend read=/data/backend/exports/customers-2026-09.csv"
PORT = int(os.environ.get("WAGENT_DEMO_PORT", "8765"))


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
            if kind == "attack":
                env = {**os.environ, "PYTHONUNBUFFERED": "1"}
                proc = subprocess.Popen(
                    ["uv", "run", "python", "-u", "tools/ask.py", ATTACK],
                    cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                )
                for line in proc.stdout:
                    self.send_line(line)
                proc.wait()
            else:
                with open(os.path.join(HERE, "recorded-run.log"), encoding="utf-8") as f:
                    for line in f:
                        self.send_line(line)
                        if not burst:
                            time.sleep(0.9 if line.startswith(("→", "←", "🛡")) else 0.25)
            self.send_line("[[done]]")
        except (BrokenPipeError, ConnectionResetError):
            pass


if __name__ == "__main__":
    print(f"Wagent demo: http://127.0.0.1:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
