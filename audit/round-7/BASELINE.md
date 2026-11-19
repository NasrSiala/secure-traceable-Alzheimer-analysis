# Baseline, round 7 — SAAMSTIAHF

Taken on 2026-11-16 before any round-7 change. State: branch `l07-chaincode-model-registry` @ `5969c89` (pushed, clean at the start of the audit) plus the owner's uncommitted `l08-gateway-history-model-routes` (T2.6, 2/2) working tree: 4 modified tracked files, 7 new files. Host: Windows 11, Git Bash, Docker 29.9.2 (Desktop, running), **no Node on the PATH** (the drive that holds it is not mounted), Python 3.14.7 via `py -3`. The TypeScript checks therefore ran in the pinned `node:20.20.2-bookworm` image, the runtime the Compose services use.

| Check | Command | Result |
|---|---|---|
| Local suite | `bash scripts/test-l.sh` | exit 0. Python: **169 passed, 1 skipped, 13 deselected** (34.15 s; `tests/scripts` alone: 158 passed, 1 skipped). Jest `chaincode/provenance`: **183 passed** (2 suites). Jest `ledger-gateway`: **201 passed** (5 suites). `tsc --noEmit` clean for both. |
| Python lint / format / types | `py -3 -m ruff check .`, `py -3 -m ruff format --check tests`, `py -3 -m mypy tests` | pass / pass (24 files) / pass (24 files) |
| Shell syntax | `bash -n` on every `fabric/*.sh`, `fabric/lib/*.sh`, `scripts/*.sh` | pass |
| Whitespace | `git diff --check` | exit 0 (CRLF notices only) |
| Dependency scan, gateway | `npm audit` in the pinned image | 0 vulnerabilities (0 with `--omit=dev`) |
| Dependency scan, chaincode | `npm audit` in the pinned image | 0 vulnerabilities |
| Fabric tests | `pytest -m fabric` | 13 collected (12 before l08). **Not run in the baseline**: about 50 minutes. Re-run in part at the end (§6 of the report). |
| Leftovers | `fabric/wallet`, `fabric/.runtime`, containers named `saam-medtrace` | none |

New tests in the l08 tree (from the counts above): Jest gateway 118 → 201 (+83: 79 in `ledger-routes.test.ts`, +4 in `routes.test.ts`, where one unknown-route case was replaced by five); Python 147 → 169 (+22: 7 in `test_model_schema_parity.py`, 15 in `test_gateway_routes_check_script.py`); Fabric 12 → 13.

Per-file Jest counts of the gateway at the baseline: `routes.test` 77, `ledger-routes.test` 79, `fabric-client.test` 14, `tokens.test` 18, `ledger-session.test` 13.

Behaviour probed before any change (`audit/round-7/tools/probe-urls.js`, `app.inject` on a build of the baseline tree):

| Request | Answer |
|---|---|
| `GET /ledger/cases/%zz`, `/ledger/models/%zz/1.0.0`, `/ledger/artifacts/%` (with or without a token) | **400** `{"error":"Bad Request","code":"FST_ERR_BAD_URL","message":"'…' is not a valid url component","statusCode":400}` (not the IF-09 envelope) |
| `GET /ledger/models/<101 characters>/1.0.0`, `/ledger/models/ecg-cnn/<101 characters>` | **414** `{"error":"Bad Request","code":"FST_ERR_MAX_PARAM_LENGTH",…}` (not the IF-09 envelope) |
| `GET /ledger/models/<100 characters>/1.0.0` | 400 `SCHEMA` (envelope) |
| trailing slash, `//ledger/…`, `/LEDGER/…`, `OPTIONS`, `PUT` | 404 `NOT_FOUND` (envelope) |
| `GET …?x=1`, `HEAD …` | 200 (the handler ran) |

Baseline failures: none. Everything that fails in the probe table is a finding (AUD-099).
