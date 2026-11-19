"""Does the real HTTP path of the NFR-03 guard honour HTTP_PROXY for a loopback gateway?

A tiny server on 127.0.0.1 answers `[]` to GET /ledger/cases/<id>. `HTTP_PROXY` points to a port
where nothing listens. If the request still arrives, the client ignores the proxy; if it fails with
"could not be reached", the token and the synthetic records would go to that proxy instead.
    py -3 audit/round-8/tools/probe_proxy.py
"""

from __future__ import annotations

import http.server
import os
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests" / "integrity"))

from gateway_history import GatewayHistory, LedgerAccessError
from synthetic_case import synthetic_case_id

seen: list[str] = []


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        seen.append(self.path)
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(b"[]")

    def log_message(self, *args: object) -> None:
        return None


server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{server.server_address[1]}"
for name in ("HTTP_PROXY", "http_proxy", "ALL_PROXY", "NO_PROXY", "no_proxy"):
    os.environ.pop(name, None)

print("without a proxy variable:", end=" ")
print(
    GatewayHistory(base, "t" * 32, timeout=5).case_history(synthetic_case_id("probe"))
)

os.environ["HTTP_PROXY"] = "http://127.0.0.1:9"
print("with HTTP_PROXY set to a dead port:", end=" ")
try:
    print(
        GatewayHistory(base, "t" * 32, timeout=5).case_history(
            synthetic_case_id("probe")
        )
    )
except LedgerAccessError as error:
    print("LedgerAccessError:", error)
print("requests that reached the gateway:", len(seen))
server.shutdown()
