# Audit inventory, round 7 — SAAMSTIAHF

Date: 2026-11-16 · Branch: `l07-chaincode-model-registry` @ `5969c89` (pushed) + the owner's uncommitted `l08-gateway-history-model-routes` (T2.6, 2/2) working tree · Source of list: `git status --short`, `git ls-files --others --exclude-standard`, `git diff --stat`.

Rounds 1 to 6 read every file that existed up to `5969c89` (round 6 read the l06 and l07 files and left no unread file). Since then 4 tracked files changed and 7 files were added by l08; the audit itself then changed or added more. Round 7 read all of them and, after the fixes, read the changed ones again (re-audit, `AUDIT_REPORT.md` §6).

Legend: `[x]` read in full, and read again after the fixes when the audit changed it · `[d]` read as a diff against `HEAD` (only imports and a test double changed) · `[=]` unchanged since the last round · `[-]` excluded.

## Gateway (`ledger-gateway/`)

- [x] `src/app.ts` (l08 routes, schemas, `LedgerSession`; **changed by audit: AUD-099**)
- [x] `src/gateway-routes-check.ts` (new, l08; **changed: AUD-101**)
- [x] `package.json` (diff: `check:routes`)
- [x] `test/ledger-routes.test.ts` (new, l08, 79 tests; **changed: AUD-099, AUD-100**, now 90)
- [x] `test/ledger-fixtures.ts` (new, l08: shared `call`, `callRaw`, `codeOf`, refusal builders)
- [d] `test/routes.test.ts` (586 lines; l08 diff: imports, a fake ledger with the three new methods, the unknown-route list)
- [=] `src/fabric-client.ts`, `src/errors.ts`, `src/tokens.ts`, `src/settings.ts`, `src/server.ts`, `src/probe-artifact.ts`, `src/gateway-check.ts`, `src/history-check.ts`, `src/model-check.ts`, `src/spike-*.ts`, `test/fabric-client.test.ts`, `test/ledger-session.test.ts`, `test/wallet-fixture.ts`, `test/tokens.test.ts`, `package-lock.json`, `.env.example` (`src/errors.ts`, `tokens.ts`, `server.ts`, `probe-artifact.ts`, `fabric-client.ts` were re-read to check the l08 code against them)

## Chaincode (`chaincode/provenance/`)

- [x] `src/model.ts` (re-read as the reference for the gateway's MODEL schema; unchanged)
- [=] everything else (no change since round 6)

## Fabric scripts (`fabric/`)

- [x] `gateway-routes-check.sh` (new, l08; untracked, mode 755 on disk)
- [x] `lib/gateway-run.sh` (**changed: AUD-102**)
- [=] `gateway-check.sh`, `history-check.sh`, `model-check.sh`, `spike-latency.sh`, `enroll-identities.sh`, `network.sh`, `deploy-chaincode.sh`, `compose/`, `config/`

## Python tests (`tests/`)

- [x] `scripts/test_model_schema_parity.py` (new, l08, 7 tests)
- [x] `scripts/test_gateway_routes_check_script.py` (new, l08, 15 tests)
- [x] `fabric/test_gateway_ledger_routes.py` (new, l08)
- [x] `fabric/fabric_support.py` (`report_line`, `assert_ok`)
- [x] `scripts/test_history_check_script.py` (**changed: AUD-102**)
- [x] `scripts/gateway_run_support.py`, `scripts/test_git_hygiene.py` (read to check how a new script is covered)
- [=] the other files of `tests/`

## Documents

- [x] `PROGRESS.md` (l08 proof row, decision row, "Trouvé, non construit", "Problèmes"; **changed: AUD-103**)
- [x] `docs/specs/02-trd.md` §8.2, `docs/specs/03-architecture.md` IF-09 and IF-10, `docs/specs/08-implementation-plan-L.md` §l08, `docs/specs/01-prd.md` AC-04.3: read as the reference (unchanged)

## Audit files

- `audit/round-7/` (this round): `BASELINE.md`, `AUDIT_REPORT.md`, `INVENTORY.md`, `CHANGES.md`, `tools/` (probe, mutation runners, live runner)
- [-] `**/node_modules`, `**/dist`, `**/dist-test`, `fabric/wallet`, `fabric/.runtime`: generated, ignored by git
