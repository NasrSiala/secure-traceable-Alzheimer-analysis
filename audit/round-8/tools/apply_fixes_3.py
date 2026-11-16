"""Third round-8 edit: the proxy test picks a free port, then binds it.

A server bound to port 0 refuses connections on the WSL2 kernel of this workstation (a port that
the kernel assigned; `audit/round-8/AUDIT_REPORT.md`, section 6). Asking the kernel for a free
port, closing the socket and binding that number explicitly connects on every host tried.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TEST = ROOT / "tests" / "integrity" / "test_no_phi_onchain.py"

raw = TEST.read_bytes()
crlf = b"\r\n" in raw
text = raw.decode("utf-8").replace("\r\n", "\n")

pairs = [
    (
        "import shutil\nimport subprocess\n",
        "import shutil\nimport socket\nimport subprocess\n",
    ),
    (
        '    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)\n',
        (
            "    # A free port, then bound by number: a server bound to port 0 refuses connections on\n"
            "    # the WSL2 kernel of the workstation.\n"
            "    with socket.socket() as probe:\n"
            '        probe.bind(("127.0.0.1", 0))\n'
            "        port = int(probe.getsockname()[1])\n"
            '    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)\n'
        ),
    ),
    (
        '        base = f"http://127.0.0.1:{server.server_address[1]}"\n',
        '        base = f"http://127.0.0.1:{port}"\n',
    ),
]
for old, new in pairs:
    if text.count(old) != 1:
        sys.exit(f"anchor found {text.count(old)} times: {old[:70]!r}")
    text = text.replace(old, new)

if crlf:
    text = text.replace("\n", "\r\n")
TEST.write_bytes(text.encode("utf-8"))
print("edited", TEST.relative_to(ROOT))
