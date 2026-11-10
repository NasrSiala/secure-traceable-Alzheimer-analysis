# Audit inventory, round 4 — SAAMSTIAHF

Date: 2026-11-10 · Branch: `l03-latency-baseline` @ `5bd6b88` (pushed) + uncommitted `l04-chaincode-create-get` (T2.5a 1/2) working tree · Source of list: `git status`, `git ls-files`.

Rounds 1 to 3 read every file that existed up to `5bd6b88`. Since then 14 tracked files changed (2 deleted) and 9 files were added. Round 4 reads all of them in full (the lockfile excepted) and re-verifies the rest with `git diff --stat HEAD`, the baseline checks and the existing cross-checks.

Legend: `[x]` read in full · `[=]` unchanged since the last round · `[-]` excluded.

## Changed or new since round 3 (read in full)

- [x] `chaincode/provenance/src/artifact.ts` (new), `provenance.ts` (new), `errors.ts` (new), `index.ts`
- [x] `chaincode/provenance/test/provenance.test.ts` (new), `jest.config.js` (new), `tsconfig.test.json` (new), `tsconfig.json`
- [x] `chaincode/provenance/package.json`
- [x] `chaincode/provenance/package-lock.json` (+4035 lines for Jest; versions, `npm audit` and `npm ci` consistency checked, not read line by line)
- [-] `chaincode/provenance/src/identity-spike.ts` (deleted; replaced by `provenance.ts`)
- [x] `fabric/deploy-chaincode.sh` (new), `fabric/scripts/deploy-chaincode.sh` (new; read against the deleted `deploy-identity-spike.sh`)
- [-] `fabric/scripts/deploy-identity-spike.sh` (deleted)
- [x] `fabric/enroll-identities.sh`, `fabric/compose/compose.yaml`, `fabric/spike-latency.sh`
- [x] `ledger-gateway/src/probe-artifact.ts` (new), `spike-latency.ts`, `spike-submit.ts`
- [x] `tests/fabric/test_identities.py`, `tests/scripts/test_node_packages.py`
- [x] `.gitignore` (`chaincode/provenance/dist-test/`), `PROGRESS.md` (diff; numbers compared with the plan and the code)

## Read as context

- [x] `docs/specs/04-backend-schema.md` §5.2, `02-trd.md` §8.2-8.3, `03-architecture.md` IF-09/IF-10, `08-implementation-plan-L.md` l04-l08, `schema.sql` (`artifact_type`), `scripts/test-l.sh`, `tests/fabric/test_latency_budget.py`, `tests/scripts/test_spike_latency_script.py`

## Unchanged since round 3

- [=] everything else in `git ls-files`

## Excluded

- [-] `node_modules/`, `dist/`, `dist-test/`, `fabric/wallet/`, `fabric/.runtime/`, `fabric/organizations/` — generated, gitignored
- [-] `.venv/`, `docs/presentation/*.pptx` — as before
