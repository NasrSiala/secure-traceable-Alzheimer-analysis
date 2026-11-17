# Audit inventory, round 2 — SAAMSTIAHF

Final state after the fixes: every line below is `[x]`, `[=]` or `[-]`; the audit added `tests/scripts/test_node_packages.py` and `audit/round-2/*`.

Date: 2026-11-09 · Branch: `l01-fabric-network` @ `8f475d4` (pushed) + uncommitted working tree · Source of list: `git ls-files` (48) + `git ls-files --others --exclude-standard` (15) = 63 files.

Round 1 (`audit/INVENTORY.md`, committed in `8f475d4`) read every file that existed then. Since that commit only 5 tracked files changed and 14 files were added (the `l02-agent-identities` / T1.4 work, still uncommitted). Round 2 therefore:

- reads **in full** every changed or new file (section "Changed or new since round 1");
- re-verifies the unchanged files by `git diff --stat HEAD` (nothing else differs from the state round 1 audited and fixed), by re-running the round-1 cross-check tools (`audit/tools/crosscheck.py`, `idcheck.py`) and the full local test suite.

Legend: `[x]` read in full · `[=]` unchanged since round 1 (still `[x]` there), re-verified by the checks above · `[-]` excluded (reason).

## Changed or new since round 1 (read in full)

### Root and docs

- [x] `PROGRESS.md` — T1.4 row, decisions and problems checked against what was run (19 passed / 1 skipped confirmed)

### `fabric/`

- [x] `fabric/network.sh` (changed: `wallet` generated and removed on stop)
- [x] `fabric/compose/compose.yaml` (changed: `ca-client` wallet mount; new profile `spike` services `cc-build`, `gw-build`, `cc-org1`, `cc-org2`, `spike`)
- [x] `fabric/enroll-identities.sh` (new, host orchestrator)
- [x] `fabric/scripts/enroll-identities.sh` (new, runs in the `ca-client` container)
- [x] `fabric/scripts/deploy-identity-spike.sh` (new, runs in the `tools` container)
- [x] `fabric/spike-submit.sh` (new)

### `chaincode/provenance/` (new, TypeScript)

- [x] `chaincode/provenance/package.json`
- [x] `chaincode/provenance/package-lock.json` (generated; versions, duplicates and integrity fields checked, not read line by line)
- [x] `chaincode/provenance/tsconfig.json`
- [x] `chaincode/provenance/src/index.ts`
- [x] `chaincode/provenance/src/identity-spike.ts`

### `ledger-gateway/` (new, TypeScript)

- [x] `ledger-gateway/package.json`
- [x] `ledger-gateway/package-lock.json` (generated; as above)
- [x] `ledger-gateway/tsconfig.json`
- [x] `ledger-gateway/src/spike-submit.ts`

### `scripts/`, `tests/`

- [x] `scripts/test-l.sh` (changed: `run_npm_test`; fixed AUD-044)
- [x] `tests/fabric/test_network.py` (changed: wallet checks; new stop test, AUD-028)
- [x] `tests/fabric/test_identities.py` (new; second enrollment added, AUD-029/031)
- [x] `tests/scripts/test_network_contract.py` (read in round 1; 4 tests added)
- [x] `tests/scripts/test_git_hygiene.py` (read in round 1; 1 test added)
- [x] `tests/scripts/test_node_packages.py` (**new in round 2**, written by the audit)
- [x] `tests/scripts/test_test_l.py` (read in round 1; 8 tests added)
- [x] `tests/scripts/test_network_helpers.py` (read in round 1; 4 tests added)
- [x] `tests/fabric/test_node_fallback.py` (**new**, written by the audit)

### `audit/`

- [x] `audit/PR_BODY.md` (round-1 artifact, untracked)
- [x] `audit/tools/apply_trd_deps_fix.py`, `audit/tools/linux_check.sh` (**new**, written by the audit)

## Unchanged since round 1

- [=] `.gitattributes`, `.gitignore`, `AGENTS.md`, `Projet 1.md`, `pytest.ini`
- [=] `fabric/config/configtx.yaml`, `fabric/scripts/enroll.sh`, `fabric/scripts/join-channel.sh`, `fabric/scripts/start-ca.sh`
- [=] `tests/conftest.py`
- [=] `docs/specs/*` (15 files: 01-prd … 08-implementation-plan-L, CHANGELOG, aar, review, traceability, schema.sql) — link check and ID census re-run: same result as round 1 (one false positive, a percent-encoded link to `Projet 1.md`)
- [=] `audit/{AUDIT_REPORT,BASELINE,CHANGES,INVENTORY}.md`, `audit/tools/*`, `audit/proposals/*` — round-1 outputs
- [=] `.gitkeep` placeholders in `chaincode/provenance`, `ledger-gateway`, `hw`

## Excluded

- [-] `docs/presentation/SAAMSTIAHF-vision-equipe.pptx` — binary, historical (round 1 inspected the package)
- [-] `.venv/` — local Python 3.10 environment, gitignored
- [-] `fabric/builders/ccaas/bin/` — empty untracked directory, removed by the audit (AUD-040)
- [-] `node_modules/`, `dist/`, `fabric/wallet/`, `fabric/.runtime/`, `fabric/organizations/` — generated at run time, gitignored
