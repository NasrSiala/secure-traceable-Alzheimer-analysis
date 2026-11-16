# Baseline, round 8 — SAAMSTIAHF

Taken on 2026-11-16 before any round-8 change. State: branch `l08-gateway-history-model-routes` @ `1c47ba6` (pushed, round 7 included) plus the owner's uncommitted `l09-no-phi-guard` (T2.9) working tree: 2 modified tracked files (`PROGRESS.md`, `pytest.ini`) and 6 new files (`fabric/gateway-serve.sh`, `tests/integrity/{gateway_history,phi_guard,synthetic_case,test_no_phi_onchain}.py`, `tests/scripts/test_gateway_serve_script.py`). Host: Windows 11, Git Bash, Docker Desktop running, **no Node on the PATH** (the TypeScript checks run in the pinned `node:20.20.2-bookworm` image), Python 3.14 via `py -3`. A second host was used for the Linux checks: WSL2 Ubuntu 22.04 (Python 3.10, kernel 6.6.87.2-microsoft-standard-WSL2).

| Check | Command | Result |
|---|---|---|
| Local suite | `bash scripts/test-l.sh` (`audit/round-8/baseline-test-l.log`) | exit 0. Python: **368 passed, 1 skipped, 24 deselected** (35.97 s). Jest `chaincode/provenance`: **183 passed**. Jest `ledger-gateway`: **212 passed**. |
| Python lint / format / types | `py -3 -m ruff check .`, `py -3 -m ruff format --check tests fabric`, `py -3 -m mypy tests` | pass / pass (29 files) / pass (29 files) |
| Shell syntax | `bash -n` on every `fabric/*.sh`, `fabric/lib/*.sh`, `scripts/*.sh` | pass |
| Fabric tests | `pytest -m fabric` | 24 collected (13 before l09, plus the 11 of `tests/integrity`). **Not run in the baseline**; the 11 new ones are run at the end (`AUDIT_REPORT.md` §6). |
| Dependency scan | `npm audit` | not run at the baseline: no JavaScript file changed since round 7 (`git status`: only Python, shell and Markdown). Re-run at the end. |
| Leftovers | `fabric/wallet`, `fabric/.runtime`, containers named `saam-medtrace` | none |

New tests in the l09 tree (from the counts above): Python 169 → 368 (+199: 177 non-network tests in `tests/integrity`, 22 in `test_gateway_serve_script.py`); Fabric 13 → 24 (+11).

Behaviour probed before any change:

| Probe | Result |
|---|---|
| 46 mutations of `phi_guard.py` (36) and `gateway_history.py` (10), `audit/round-8/tools/mutate_guard.py` | 40 killed, **6 survived**: `docType` not checked (M01), end of the era 2099 (M10), key of a field outside the schema not read for patterns (M14), birth words (M25), titles with a full stop (M28), trailing slash of the base URL (G07). One more (M32) was not applied at first because of a wrong anchor in the tool, then killed. `audit/round-8/mutations-guard.log` |
| `audit/round-8/tools/orphan-probe.sh` on WSL2 (real Linux), the real `gateway-serve.sh` and `gateway-run.sh` with a stub `npm` | `SIGTERM` to the script: **the gateway stays running** (AUD-106) |
| `audit/round-8/tools/probe_proxy.py`: a server on the loopback, `HTTP_PROXY` pointing to a dead port | the real HTTP path fails with "the gateway could not be reached": the request went to the proxy (AUD-110) |
| `audit/round-8/tools/probe_guard.py`: values written in `softwareVersion` | 9 of 18 candidate values are not flagged where the project's policy would flag them (AUD-109) |
| `grep` of the names in `fabric/lib/gateway-run.sh` against the scripts that source it | `gateway-serve.sh` sources it and is not named (AUD-107) |

Baseline failures: none. Everything listed as surviving or not flagged above is a finding.
