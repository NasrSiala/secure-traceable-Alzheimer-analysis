# Audit inventory, round 5 — SAAMSTIAHF

Date: 2026-11-11 · Branch: `l04-chaincode-create-get` @ `571e933` (pushed) + uncommitted `l05-gateway-artifact-routes` (T2.6 1/2) working tree · Source of list: `git status`, `git ls-files`.

Rounds 1 to 4 read every file that existed up to `571e933`. Since then 6 tracked files changed and 11 files or directories were added; the audit itself then added or changed more. Round 5 read all of them in full (the lockfile excepted) and, after the fixes, read the changed ones again (re-audit, `AUDIT_REPORT.md` §6).

Legend: `[x]` read in full, and read again after the fixes when the audit changed it · `[=]` unchanged since the last round · `[-]` excluded.

## Gateway sources (`ledger-gateway/src/`)

- [x] `app.ts` (new; changed by audit: AUD-069, 071, 074)
- [x] `errors.ts` (new; changed: AUD-071, 078)
- [x] `tokens.ts` (new; changed: AUD-086 `identities()`, message split)
- [x] `fabric-client.ts` (new; changed: AUD-072, 073, 086, 087)
- [x] `server.ts` (new; changed: AUD-071, 073, 086, 090)
- [x] `gateway-check.ts` (new; changed: AUD-070, 071, 073, 089)
- [x] `settings.ts` (added by the audit: AUD-073, 088)
- [x] `spike-submit.ts` (rewritten by the owner to go through the gateway app; changed: AUD-073)
- [x] `spike-latency.ts` (changed: AUD-073 only)
- [x] `probe-artifact.ts` (unchanged; read as dependency of the checks)

## Gateway tests and configuration

- [x] `test/routes.test.ts` (new; rewritten: AUD-069, 074, 078, 079)
- [x] `test/tokens.test.ts` (new; extended: AUD-079, 086)
- [x] `test/fabric-client.test.ts` (added by the audit: AUD-072, 073, 086, 087, 088)
- [x] `jest.config.js`, `tsconfig.test.json` (new), `tsconfig.json`
- [x] `package.json` (changed: AUD-075, 076, 080)
- [x] `package-lock.json` (+4495 lines for Fastify and Jest; regenerated in the pinned image; versions, `npm audit` and `npm ci` consistency checked, not read line by line)
- [x] `.env.example` (new; changed: AUD-073)

## Fabric scripts and Python tests

- [x] `fabric/gateway-check.sh` (new; changed: AUD-077)
- [x] `tests/fabric/test_gateway_artifacts.py` (new; changed: AUD-070, 071)
- [x] `tests/scripts/test_node_packages.py` (changed by the owner; extended: AUD-061/076, 073, 075, 080)
- [x] `tests/scripts/test_gateway_check_script.py` (added by the audit: AUD-077)
- [x] `tests/scripts/test_artifact_schema_parity.py` (added by the audit: AUD-081)

## Tracking

- [x] `.gitignore` (`ledger-gateway/dist-test/`)
- [x] `PROGRESS.md` (diff; numbers compared with the plan and the code; updated for round 5)

## Read as context

- [x] `docs/specs/02-trd.md` §8.2, §9, §18, `03-architecture.md` IF-09/IF-10, `08-implementation-plan-L.md` l05/l08, `05-system-design.md` FM-03/FM-13
- [x] `chaincode/provenance/src/artifact.ts`, `errors.ts` (schema constants and error text the gateway parses)
- [x] `fabric/spike-latency.sh`, `fabric/spike-submit.sh`, `fabric/compose/compose.yaml` (`spike` service), `fabric/enroll-identities.sh` (build step)
- [x] `scripts/test-l.sh`, `tests/conftest.py`, `tests/fabric/test_identities.py`, `tests/scripts/test_git_hygiene.py`, `tests/scripts/test_spike_latency_script.py` (harness), `audit/tools/linux_check.sh`

## Unchanged since round 4

- [=] everything else in `git ls-files`
