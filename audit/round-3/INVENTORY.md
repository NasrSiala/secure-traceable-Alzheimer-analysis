# Audit inventory, round 3 — SAAMSTIAHF

Date: 2026-11-10 · Branch: `l02-agent-identities` @ `f37e865` (pushed) + uncommitted `l03-latency-baseline` (T1.8) working tree · Source of list: `git ls-files` + `git ls-files --others --exclude-standard`.

Rounds 1 and 2 read every file that existed up to `f37e865`. Since that commit only 2 tracked files changed and 3 files were added (the T1.8 work). Round 3 therefore reads those five in full and re-verifies the rest by `git diff --stat f37e865` (nothing else differs), the baseline checks and the cross-check tools.

Legend: `[x]` read in full · `[=]` unchanged since the last round, re-verified · `[-]` excluded.

## Changed or new since round 2 (read in full)

- [x] `PROGRESS.md` (diff: T1.8 row, state lines, `BatchTimeout` decision; numbers re-derived from the listed samples: p50 rank 4 = 2,084254, p95 rank 7 = 2,262708)
- [x] `ledger-gateway/package.json` (diff: script `spike:latency`)
- [x] `ledger-gateway/src/spike-latency.ts` (new)
- [x] `fabric/spike-latency.sh` (new)
- [x] `tests/fabric/test_latency_budget.py` (new)

## Read as context

- [x] `fabric/compose/compose.yaml`, `fabric/config/configtx.yaml`, `fabric/scripts/deploy-identity-spike.sh`, `ledger-gateway/src/spike-submit.ts`, `ledger-gateway/tsconfig.json`, `chaincode/provenance/src/identity-spike.ts`, `tests/conftest.py`, `tests/scripts/test_test_l.py`, `docs/specs/08-implementation-plan-L.md` §6 (l03), `docs/specs/05-system-design.md` §10

## Unchanged since round 2

- [=] everything else in `git ls-files` (63 files at round 2, plus the round-2 outputs committed in `f37e865`)

## Excluded

- [-] `node_modules/`, `dist/`, `fabric/wallet/`, `fabric/.runtime/`, `fabric/organizations/` — generated, gitignored
- [-] `.venv/`, `docs/presentation/*.pptx` — as in round 2
