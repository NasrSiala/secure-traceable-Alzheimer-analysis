# Audit inventory, round 8 — SAAMSTIAHF

Date: 2026-11-16 · Branch: `l08-gateway-history-model-routes` @ `1c47ba6` (pushed) + the owner's uncommitted `l09-no-phi-guard` (T2.9) working tree · Source of list: `git status --short -uall`, `git diff --stat`.

Rounds 1 to 7 read every file that existed up to `1c47ba6` (round 7 read the l08 tree in full and again after its fixes). Since then 2 tracked files changed and 6 files were added by l09; the audit itself then changed or added more. Round 8 read all of them and, after the fixes, read the changed ones again (`AUDIT_REPORT.md` §6).

Legend: `[x]` read in full, and read again after the fixes when the audit changed it · `[d]` read as a diff against `HEAD` · `[=]` unchanged since the last round · `[-]` excluded.

## Test support (`tests/integrity/`, new, l09)

- [x] `phi_guard.py` (the guard: schema, formats, name and date-of-birth patterns, diagnostics)
- [x] `gateway_history.py` (the `httpx` path to the gateway; **changed by audit: AUD-110**)
- [x] `synthetic_case.py` (deterministic synthetic records)
- [x] `test_no_phi_onchain.py` (863 lines, 177 non-network and 11 network tests; **changed by audit: AUD-106, AUD-108, AUD-110**, now 216 and 11)
- [x] `process_tree.py` (**new, audit: AUD-106**)

## Fabric scripts (`fabric/`)

- [x] `gateway-serve.sh` (new, l09; untracked, mode 755 on disk; **changed: header, AUD-106**)
- [x] `lib/gateway-run.sh` (**changed: AUD-107**)
- [=] `gateway-check.sh`, `history-check.sh`, `model-check.sh`, `gateway-routes-check.sh`, `spike-latency.sh`, `enroll-identities.sh`, `network.sh`, `deploy-chaincode.sh`, `compose/`, `config/`

## Python tests (`tests/`)

- [x] `scripts/test_gateway_serve_script.py` (new, l09, 22 tests)
- [x] `scripts/test_history_check_script.py` (**changed: AUD-107**)
- [x] `scripts/gateway_run_support.py`, `conftest.py`, `fabric/fabric_support.py` (read to check how the new files use them)
- [=] the other files of `tests/`

## Configuration and documents

- [d] `pytest.ini` (`pythonpath = tests/fabric`)
- [x] `PROGRESS.md` (T2.9 proof row, decision row, "Problèmes", "Trouvé, non construit"; **changed: AUD-111**)
- [x] `docs/specs/08-implementation-plan-L.md` §l09, `docs/specs/02-trd.md` (NFR-03, §8.2), `docs/specs/04-backend-schema.md` §5.2 (`softwareVersion`, `modelVersion`), `AGENTS.md`: read as the reference (unchanged)
- [=] `ledger-gateway/`, `chaincode/provenance/` (no change since round 7; `src/server.ts` and `src/settings.ts` were re-read to check the environment variables that `gateway-serve.sh` hands over)

## Audit files

- `audit/round-8/` (this round): `BASELINE.md`, `AUDIT_REPORT.md`, `INVENTORY.md`, `CHANGES.md`, logs, `tools/` (mutation runners, probes, edit scripts)
- [-] `**/node_modules`, `**/dist`, `**/dist-test`, `fabric/wallet`, `fabric/.runtime`, `__pycache__`: generated, ignored by git
