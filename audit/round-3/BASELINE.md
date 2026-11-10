# Baseline, round 3 — SAAMSTIAHF

Taken on 2026-11-10 before any round-3 change. State: branch `l02-agent-identities` @ `f37e865` (pushed) plus the uncommitted `l03-latency-baseline` (T1.8) working tree: `PROGRESS.md` and `ledger-gateway/package.json` modified; `fabric/spike-latency.sh`, `ledger-gateway/src/spike-latency.ts`, `tests/fabric/test_latency_budget.py` new. Host: Windows 11, Git Bash, Docker 29.9.2 (Desktop), Node 22.17.0, npm 11.12.1, Python via `py -3`.

| Check | Command | Result |
|---|---|---|
| Local test suite | `bash scripts/test-l.sh` | **55 passed, 1 skipped, 9 deselected** (14 s). The skip is the POSIX-only permission test. The 4 new tests are in `tests/fabric/test_latency_budget.py`. |
| TypeScript tests on the host | `npm test` in `chaincode/provenance`, `ledger-gateway` (called by `test-l.sh`) | pass (`tsc --noEmit`, both packages, includes `spike-latency.ts`) |
| Python lint | `ruff check .` | pass |
| Python format | `ruff format --check .` | **FAIL**: 1 file would be reformatted (`tests/fabric/test_latency_budget.py`); round 2 ended with 40 files clean |
| Python types | `mypy tests` | pass (10 source files) |
| Shell syntax | `bash -n fabric/spike-latency.sh` | pass |
| Dependency scan | `npm audit` in `ledger-gateway` (no dependency changed) | 0 vulnerabilities |
| Fabric suite | not re-run at baseline: PROGRESS.md records `test-l.sh --fabric` 55 passed, 1 skipped, then 9 passed in 727,93 s for this tree (taken as the owner's result; re-run after the fixes) | not re-run |
| Standalone DoD command | `cd ledger-gateway && npm run spike:latency` (no network, no extra environment) | **fails**: `environment unavailable: BATCH_TIMEOUT is required` (AUD-049) |
| Exit-code contract | old `fabric/spike-latency.sh` in a scratch tree with a stub `npm` whose `run build` exits 2 (what `tsc` returns on a type error) | **exit 2**, the code the script documents as "measured budget breach" (AUD-048) |
| Production build / app start | n/a | no application code yet |

Pre-existing at baseline: format check (new with the l03 test file), nothing else red.
