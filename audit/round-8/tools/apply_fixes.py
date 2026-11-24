"""Round-8 edits to the owner's l09 files, applied as bytes so that CRLF files stay CRLF.

Each edit asserts that its anchor occurs exactly once. Run it once on the tree as the owner left
it; a second run stops at the first anchor it no longer finds.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def edit(path: Path, pairs: list[tuple[str, str]]) -> None:
    raw = path.read_bytes()
    crlf = b"\r\n" in raw
    text = raw.decode("utf-8").replace("\r\n", "\n")
    for old, new in pairs:
        if text.count(old) != 1:
            sys.exit(f"{path.name}: anchor found {text.count(old)} times: {old[:60]!r}")
        text = text.replace(old, new)
    if crlf:
        text = text.replace("\n", "\r\n")
    path.write_bytes(text.encode("utf-8"))
    print("edited", path.relative_to(ROOT))


TEST = ROOT / "tests" / "integrity" / "test_no_phi_onchain.py"
HISTORY = ROOT / "tests" / "integrity" / "gateway_history.py"

edit(
    HISTORY,
    [
        (
            """            with httpx.Client(
                transport=self._transport, timeout=self._timeout
            ) as client:""",
            """            # trust_env=False: the gateway is called directly. With the default, an
            # HTTP_PROXY of the environment would carry the token and the records to the proxy
            # (AUD-110).
            with httpx.Client(
                transport=self._transport, timeout=self._timeout, trust_env=False
            ) as client:""",
        )
    ],
)

edit(
    TEST,
    [
        # --- imports
        (
            "import shutil\nimport subprocess\n",
            "import shutil\nimport signal\nimport subprocess\nimport sys\n",
        ),
        (
            "import tempfile\nimport time\n",
            "import tempfile\nimport threading\nimport time\n",
        ),
        (
            "from collections.abc import Callable, Iterator\n",
            (
                "from collections.abc import Callable, Iterator\n"
                "from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer\n"
            ),
        ),
        # --- AUD-108: docType, and the key of a field
        (
            """def test_a_missing_field_is_detected() -> None:""",
            """def test_a_doc_type_other_than_artifact_is_detected() -> None:
    records = clean_history("unit")
    only_record(records)["docType"] = "model"

    found = phi_guard.check_history(records)

    assert "format" in kinds(found)
    assert {violation.field for violation in found} == {"docType"}


def test_a_name_or_a_date_used_as_the_name_of_a_field_is_read() -> None:
    \"\"\"The key of a field outside the schema can carry the identity as well as its value.\"\"\"
    records = clean_history("unit")
    only_record(records)["Jean Dupont"] = 1
    only_record(records)["1975-03-12"] = 1

    found = kinds(phi_guard.check_history(records))

    assert {"unknown_field", "name_pattern", "dob_pattern"} <= found


def test_a_missing_field_is_detected() -> None:""",
        ),
        # --- AUD-108: the end of the era
        (
            """@pytest.mark.parametrize("value", ["1975-03-12T00:00:00.000Z", "2001-01-01T00:00:00Z"])
def test_a_timestamp_far_from_the_project_era_is_detected(""",
            """@pytest.mark.parametrize(
    "value",
    [
        "1975-03-12T00:00:00.000Z",
        "2001-01-01T00:00:00Z",
        "2019-12-31T23:59:59Z",
        "2100-01-01T00:00:00Z",
        "2150-01-01T00:00:00.000Z",
    ],
)
def test_a_timestamp_far_from_the_project_era_is_detected(""",
        ),
        (
            """@pytest.mark.parametrize("field", ["createdAt", "txTimestamp"])
@pytest.mark.parametrize(
    "value", ["12/03/2026", "2026-11-09", "not a date", "2026-11-09 12:00:00"]
)""",
            """@pytest.mark.parametrize("field", ["createdAt", "txTimestamp"])
@pytest.mark.parametrize(
    "value",
    ["2020-01-01T00:00:00Z", "2026-11-09T12:00:00.123456789Z", "2099-12-31T23:59:59Z"],
)
def test_a_timestamp_inside_the_project_era_passes(field: str, value: str) -> None:
    records = clean_history("unit")
    only_record(records)[field] = value

    assert phi_guard.check_history(records) == []


@pytest.mark.parametrize("field", ["createdAt", "txTimestamp"])
@pytest.mark.parametrize(
    "value", ["12/03/2026", "2026-11-09", "not a date", "2026-11-09 12:00:00"]
)""",
        ),
        # --- AUD-108: birth words and titles
        (
            """NAMES = [""",
            """BIRTH_WORDS = ["dob", "born", "naissance", "birth", "birthdate", "birthday"]


@pytest.mark.parametrize("value", BIRTH_WORDS)
@pytest.mark.parametrize("field", ["softwareVersion", "modelVersion"])
def test_a_birth_word_alone_is_detected_in_a_free_field(value: str, field: str) -> None:
    records = clean_history("unit")
    only_record(records)[field] = value

    found = phi_guard.check_history(records)

    assert "dob_pattern" in kinds(found)
    assert field in {violation.field for violation in found}


# A title followed by a full stop is not read as a name by the first pattern (a capitalised word
# and a capitalised word); the title pattern is the one that finds it.
TITLED_NAMES = ["M. Martin", "Mr. Dupont", "Dr. Dupont", "Mlle. Durand", "Pr. Curie"]


@pytest.mark.parametrize("value", TITLED_NAMES)
@pytest.mark.parametrize("field", ["softwareVersion", "modelVersion"])
def test_a_title_and_a_name_is_detected_in_a_free_field(value: str, field: str) -> None:
    records = clean_history("unit")
    only_record(records)[field] = value

    assert "name_pattern" in kinds(phi_guard.check_history(records))


NAMES = [""",
        ),
        # --- AUD-108 (trailing slash) and AUD-110 (proxy): the http path
        (
            """def test_an_artifact_is_created_through_the_gateway_with_the_body_as_given() -> None:""",
            """def test_a_base_url_with_a_trailing_slash_does_not_double_it() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[])

    source = GatewayHistory(
        "http://gateway.test/", TOKEN, transport=httpx.MockTransport(handler)
    )
    source.case_history(synthetic_case_id("unit"))
    source.create_artifact({})

    assert [request.url.path for request in seen] == [
        f"/ledger/cases/{synthetic_case_id('unit')}",
        "/ledger/artifacts",
    ]


def test_the_gateway_is_called_directly_whatever_the_proxy_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    \"\"\"AUD-110. A real server on the loopback and a proxy variable that points nowhere: with the
    environment trusted, the request would go to the proxy, token and records included.\"\"\"
    seen: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            seen.append(self.path)
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(b"[]")

        def log_message(self, *_args: object) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    for name in ("NO_PROXY", "no_proxy"):
        monkeypatch.delenv(name, raising=False)
    for name in ("HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.setenv(name, "http://127.0.0.1:9")
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        records = GatewayHistory(base, TOKEN, timeout=10).case_history(
            synthetic_case_id("unit")
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)

    assert records == []
    assert seen == [f"/ledger/cases/{synthetic_case_id('unit')}"]


def test_an_artifact_is_created_through_the_gateway_with_the_body_as_given() -> None:""",
        ),
        # --- AUD-106: stop what the script started
        (
            """def _wait_until_serving(""",
            """def _spawn(args: list[str], env: dict[str, str]) -> subprocess.Popen[str]:
    \"\"\"Run `bash <args>` from the repository root, as the leader of a process group on POSIX.\"\"\"
    return subprocess.Popen(
        [bash_executable(), *args],
        cwd=ROOT,
        env={**os.environ, **env},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        start_new_session=sys.platform != "win32",
    )


def _stop_tree(process: subprocess.Popen[str]) -> None:
    \"\"\"Stop a process and everything it started (AUD-106).

    A signal to fabric/gateway-serve.sh alone ends the script and leaves npm and the gateway
    running, with their port and their wallet. On POSIX the script leads a group of its own
    (see `_spawn`), and the group gets the signal; on Windows `taskkill /T` walks the tree.\"\"\"
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            capture_output=True,
            check=False,
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def test_stopping_the_serve_process_stops_what_it_started(tmp_path: Path) -> None:
    \"\"\"The gateway is a grandchild of the script. After `_stop_tree` it is gone, not orphaned
    (`audit/round-8/tools/orphan-probe.sh` shows the orphan when only the script is signalled).\"\"\"
    pid_file = tmp_path / "grandchild.pid"
    process = _spawn(
        ["-c", f'sleep 300 & echo $! > "{pid_file.as_posix()}"; wait'], {}
    )
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and not (
        pid_file.exists() and pid_file.read_text().strip()
    ):
        time.sleep(0.2)
    grandchild = pid_file.read_text().strip()
    assert grandchild.isdigit(), "the script did not start its child"

    _stop_tree(process)

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
    assert process.poll() is not None


def _wait_until_serving(""",
        ),
        (
            """        process = subprocess.Popen(
            [bash_executable(), "fabric/gateway-serve.sh"],
            cwd=ROOT,
            env={**os.environ, **env},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )""",
            """        process = _spawn(["fabric/gateway-serve.sh"], env)""",
        ),
        (
            """        if process is not None and process.poll() is None:
            process.terminate()
""",
            """        if process is not None:
            _stop_tree(process)
""",
        ),
    ],
)
