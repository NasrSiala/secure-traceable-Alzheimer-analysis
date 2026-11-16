# Audit inventory, round 6 — SAAMSTIAHF

Date: 2026-11-15 · Branch: `l06-chaincode-provenance-rules` @ `15dd22e` (pushed) + uncommitted `l07-chaincode-model-registry` (T2.5b) working tree · Source of list: `git diff --name-status 36a8bcb`, `git ls-files --others --exclude-standard`.

Rounds 1 to 5 read every file that existed up to `36a8bcb` (l05). Since then 24 tracked files changed (l06 commits `a8f7b42`, `15dd22e`, then the l07 edits) and 7 files were added by l07; the audit itself then added or changed more. Round 6 read all of them (see `AUDIT_REPORT.md` §2 for the two files read as diffs) and, after the fixes, read the changed ones again (re-audit, `AUDIT_REPORT.md` §6).

Legend: `[x]` read in full, and read again after the fixes when the audit changed it · `[d]` read as a diff against `36a8bcb` (the file is large and its l06 part was reviewed in the l06 code review) · `[=]` unchanged since the last round · `[-]` excluded.

## Chaincode (`chaincode/provenance/`)

- [x] `src/model.ts` (new, l07)
- [x] `src/provenance.ts` (l06 parent rules, history, event, `INTEGRITY`; l07 `RegisterModel`, `GetModel`)
- [x] `src/artifact.ts` (l06 `requireCaseId`; l07 exports `SHA256`, `isRecord`, `requireString`)
- [x] `src/errors.ts` (l06: `PARENT_MISSING`, `INTEGRITY`)
- [x] `test/memory-ledger.ts` (new, l07: the stand-in ledger moved out of `provenance.test.ts`)
- [x] `test/model-registry.test.ts` (new, l07, 95 tests)
- [d] `test/provenance.test.ts` (689 lines; the 48 `describe` / `test` declarations are the same before and after l07: sorted diff of the declaration lines; the l07 diff only removes the stand-in ledger)
- [=] `package.json`, `package-lock.json`, `jest.config.js`, `tsconfig.json`, `tsconfig.test.json`, `src/index.ts`

## Gateway (`ledger-gateway/`)

- [x] `src/fabric-client.ts` (l06 `history`; l07 `registerModel`, `getModel`; **changed by audit: AUD-091**)
- [x] `src/errors.ts` (l06 `describeCause`, `details[]`)
- [x] `src/gateway-check.ts` (l06 forged-creator attempt)
- [x] `src/history-check.ts` (new, l06; **changed: AUD-094**)
- [x] `src/model-check.ts` (new, l07)
- [x] `package.json` (`check:history`, `check:model`)
- [d] `test/routes.test.ts` (586 lines; l06 diff: creator fields from the client, cause from `details`)
- [x] `test/fabric-client.test.ts` (changed by audit: shares the wallet fixture)
- [x] `test/wallet-fixture.ts` (added by the audit: AUD-091)
- [x] `test/ledger-session.test.ts` (added by the audit: AUD-091, 13 tests)
- [=] `src/app.ts`, `src/server.ts`, `src/tokens.ts`, `src/settings.ts`, `src/probe-artifact.ts`, `src/spike-*.ts`, `test/tokens.test.ts`, `package-lock.json`, `.env.example`

## Fabric scripts (`fabric/`)

- [x] `lib/gateway-run.sh` (new, l06; **changed: AUD-093**)
- [x] `gateway-check.sh`, `history-check.sh` (new, l06), `model-check.sh` (new, l07), `spike-latency.sh`
- [x] `enroll-identities.sh` (`deploy_chaincode`, `write_chaincode_packages`: read to check the l07 claim that the sequence does not change; unchanged)
- [=] `network.sh`, `deploy-chaincode.sh`, `scripts/`, `compose/`, `config/`

## Python tests (`tests/`)

- [x] `conftest.py` (l06 `_stop_after_test`)
- [x] `fabric/fabric_support.py` (new, l06)
- [x] `fabric/test_case_history.py` (new, l06), `fabric/test_model_registry.py` (new, l07)
- [x] `fabric/test_gateway_artifacts.py`, `fabric/test_identities.py`, `fabric/test_latency_budget.py` (l06: shared helpers; diffs read)
- [x] `scripts/gateway_run_support.py` (added by the audit: AUD-092)
- [x] `scripts/test_gateway_check_script.py`, `scripts/test_history_check_script.py` (new, l06), `scripts/test_model_check_script.py` (new, l07) (**changed: AUD-092, AUD-093**)
- [x] `scripts/test_deploy_chaincode_script.py` (l07: two tests on the definition and the package)
- [=] the other files of `tests/`

## Documents

- [x] `PROGRESS.md` (l06 and l07 rows, decisions; **audit row added**)
- [x] `docs/specs/04-backend-schema.md` §5.2, `docs/specs/schema.sql` (`models`), `docs/specs/08-implementation-plan-L.md` §l07, `docs/specs/02-trd.md` §8.2–8.3: read as the reference for MODEL (unchanged)
- [-] `**/node_modules`, `**/dist`, `**/dist-test`, `fabric/wallet`, `fabric/.runtime`: generated, ignored by git
