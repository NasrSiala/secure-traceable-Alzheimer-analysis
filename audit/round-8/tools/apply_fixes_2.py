"""Second round-8 edit: the integrity test uses `process_tree.ProcessTree` (see process_tree.py).

Replaces the first attempt of apply_fixes.py (a `taskkill /T` walk, which misses the programs that
Git Bash starts: see AUDIT_REPORT.md, AUD-106). Bytes in, bytes out, so CRLF stays CRLF.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TEST = ROOT / "tests" / "integrity" / "test_no_phi_onchain.py"

raw = TEST.read_bytes()
crlf = b"\r\n" in raw
text = raw.decode("utf-8").replace("\r\n", "\n")

start = text.index("def _spawn(")
end = text.index("def _wait_until_serving(")
new_block = '''def test_stopping_the_serve_process_stops_what_it_started(tmp_path: Path) -> None:
    """The gateway is a grandchild of the script. After `stop` it is gone, not orphaned
    (`audit/round-8/tools/orphan-probe.sh` shows the orphan when only the script is signalled)."""
    pid_file = tmp_path / "grandchild.pid"
    tree = ProcessTree(
        [bash_executable(), "-c", f'sleep 300 & echo $! > "{pid_file.as_posix()}"; wait'],
        cwd=ROOT,
        env=dict(os.environ),
    )
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and not (
        pid_file.exists() and pid_file.read_text().strip()
    ):
        time.sleep(0.2)
    grandchild = pid_file.read_text().strip()
    assert grandchild.isdigit(), "the script did not start its child"

    tree.stop()

    gone = False
    for _ in range(50):
        probe = subprocess.run(
            [bash_executable(), "-c", f"kill -0 {grandchild} 2>/dev/null"],
            capture_output=True,
            check=False,
        )
        if probe.returncode != 0:
            gone = True
            break
        time.sleep(0.2)
    if not gone:
        subprocess.run([bash_executable(), "-c", f"kill -9 {grandchild}"], check=False)
    assert gone, "the child of the script is still running after the stop"
    assert tree.process.poll() is not None


'''
text = text[:start] + new_block + text[end:]

pairs = [
    (
        "def _wait_until_serving(source: GatewayHistory, process: subprocess.Popen[str]) -> None:",
        "def _wait_until_serving(source: GatewayHistory, process: subprocess.Popen[str]) -> None:",
    ),
    (
        "    process: subprocess.Popen[str] | None = None\n",
        "    serve: ProcessTree | None = None\n",
    ),
    (
        '        process = _spawn(["fabric/gateway-serve.sh"], env)\n',
        (
            "        serve = ProcessTree(\n"
            '            [bash_executable(), "fabric/gateway-serve.sh"],\n'
            "            cwd=ROOT,\n"
            "            env={**os.environ, **env},\n"
            "        )\n"
        ),
    ),
    (
        "        _wait_until_serving(reader, process)\n",
        "        _wait_until_serving(reader, serve.process)\n",
    ),
    (
        "        if process is not None:\n            _stop_tree(process)\n",
        "        if serve is not None:\n            serve.stop()\n",
    ),
    (
        "from phi_guard import ARTIFACT_FIELDS, Violation\n",
        "from phi_guard import ARTIFACT_FIELDS, Violation\nfrom process_tree import ProcessTree\n",
    ),
]
for old, new in pairs:
    if text.count(old) != 1:
        sys.exit(f"anchor found {text.count(old)} times: {old[:70]!r}")
    text = text.replace(old, new)

# `signal` and `sys` were imported for the first attempt only.
for module in ("import signal\n", "import sys\n"):
    if re.search(rf"^{re.escape(module)}", text, re.MULTILINE) is None:
        sys.exit(f"{module!r} not found")
    text = text.replace(module, "", 1)

if crlf:
    text = text.replace("\n", "\r\n")
TEST.write_bytes(text.encode("utf-8"))
print("edited", TEST.relative_to(ROOT))
