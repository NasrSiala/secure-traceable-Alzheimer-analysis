# Audit report, round 6 — SAAMSTIAHF

Date: 2026-11-15 · Scope: the committed `l06-chaincode-provenance-rules` work (T2.5a 2/2, `a8f7b42` and `15dd22e`, never audited as a whole: it had a code review) and the uncommitted `l07-chaincode-model-registry` (T2.5b) working tree, both on top of `l05-gateway-artifact-routes` @ `36a8bcb`. Earlier rounds: `audit/`, `audit/round-2/` to `audit/round-5/`. Finding IDs continue from AUD-090.

## 1. Summary

l06 adds the parent rules, `GetCaseHistory`, the `ArtifactAnchored` event and the `INTEGRITY` code to the chaincode, the history and forged-creator probes, and the shared `fabric/lib/gateway-run.sh`. l07 adds `RegisterModel` and `GetModel` (`model.ts`), a shared stand-in ledger for the Jest tests (`test/memory-ledger.ts`), `LedgerSession.registerModel` / `getModel`, the `model-check` probe (`model-check.ts`, `fabric/model-check.sh`) and its tests. It matches Schema §5.2 (MODEL), TRD §8.3, AC-04.3 and plan l07: `role=model-admin` is compared exactly and checked before the schema and the duplicate, the closed schema refuses every field outside `name`, `version`, `sha256`, `framework`, the key is the composite key `model` (name, version), a duplicate never overwrites, a missing model is `NOT_FOUND`, and a registered model does not appear in any case history.

No defect was found in the chaincode: the logic of `RegisterModel`, `GetModel`, the parent rules and the ordering held under reading, and the l07 tests have teeth: 15 of 16 mutations of the MODEL code are caught, the 16th is equivalent (section 6). The findings are in the gateway client, the probes and the script tests, and are all small: the three new session methods are not covered by any gateway test (a transaction name or a submit/evaluate swap would pass 105 tests), and the check scripts and their tests were copied again.

| Severity | Count | IDs |
|---|---|---|
| Critical / High / Medium | 0 | |
| Low | 4 | AUD-091, AUD-092, AUD-093, AUD-094 |
| Info | 4 | AUD-095, AUD-096, AUD-097, AUD-098 |

Decisions needed from the user: none blocking. AUD-095 (public code for `INTEGRITY`) joins the open AUD-082 and AUD-084 decisions for you or B; AUD-096 (a lint command that does not exist) and AUD-098 (a plan sentence that is now wrong) are for the spec owner.

## 2. Coverage

All 31 files changed since `36a8bcb` were read: the 7 new files in full, the 24 others as diffs against `36a8bcb` and, for the ones the l07 work touches, in full. The two files too large to read again line by line are `chaincode/provenance/test/provenance.test.ts` (689 lines: declaration list compared with `HEAD`, diff read; its 13 l06 tests were read in the l06 code review) and `ledger-gateway/test/routes.test.ts` (586 lines: l06 diff read). One line per file in `INVENTORY.md`. The lockfiles did not change.

## 3. Baseline

See `BASELINE.md`: local suite exit 0 (Python 147 passed / 1 skipped, Jest 183 chaincode and 105 gateway), ruff, format and mypy clean, `npm audit` 0 for both packages. The Fabric suite was not run at baseline.

## 4. Findings

### AUD-091 — Low — Test/Architecture — three gateway session methods are untested and the call set-up is copied five times
- **Location:** `ledger-gateway/src/fabric-client.ts:152-185` (`create`, `read`, `history`, `registerModel`, `getModel`)
- **Description:** each method repeats `sessionFor` → `getNetwork().getContract()` → `withDeadline(submit|evaluate)` → `Buffer.from(...).toString("utf8")`. l06 added `history` (the code review skipped the duplication, "to factor with the l08 route") and l07 added two more copies. No Jest test calls `history`, `registerModel` or `getModel`: the transaction name and the choice between `submitTransaction` and `evaluateTransaction` are only checked by the Fabric suite, about 50 minutes.
- **Evidence:** in a copy of the package, `registerModel` changed to `evaluateTransaction`, `history` to the name `GetCaseHistoryX`, `getModel` to `(version, name)`: `npm test` → 105 passed (`BASELINE.md`). `grep -n "history\|registerModel\|getModel" ledger-gateway/test/*.ts` finds nothing.
- **Root cause:** the l06 and l07 increments each added a method by copying its neighbour, and the existing session tests only drive `read` against an endpoint that is down.
- **Impact:** l08 will route `POST /ledger/models` and `GET /ledger/cases/{id}` through these methods; a typo there fails at the first live run, not in `npm test`. A `registerModel` that evaluates instead of submitting would answer a record that was never written.
- **Recommended fix:** one private `submit` and one `evaluate` helper (session, contract, deadline, decoding) so each method is a line that names its transaction; a Jest file that replaces `connect` of `@hyperledger/fabric-gateway` and asserts, for the five methods, the identity, the transaction name, the arguments and the kind.
- **Status:** Fixed. `fabric-client.ts` has one `submit` and one `evaluate`; `test/ledger-session.test.ts` (13 tests, shared `test/wallet-fixture.ts`) asserts identity, channel, chaincode, contract, transaction, arguments and kind for the five methods, the pass-through of the peer's refusal, one session per identity. Gateway Jest 105 → 118. 8 mutations of the client all fail at least one test (before: 3 of them left 105 passed). Live on a fresh network: `gateway-check.sh`, `history-check.sh`, `model-check.sh` exit 0.

### AUD-092 — Low — Test — the contract tests of the three check scripts are three copies
- **Location:** `tests/scripts/test_gateway_check_script.py:19-67`, `tests/scripts/test_history_check_script.py:18-65`, `tests/scripts/test_model_check_script.py:19-66`
- **Description:** the fake `npm`, the fake `docker`, the `HOST` and `CONTAINER` set-ups and `_run` are the same 50 lines in each file; only the script name and the npm script differ. l06's code review removed the same kind of duplication in the shell scripts and in the Fabric test helpers; l07 added the third copy of the test side.
- **Evidence:** `diff` of the helper blocks of the history and model files: two differing words (`history` / `model`).
- **Root cause:** each increment copied the previous script's test file.
- **Impact:** a change to the dispatch contract (a new environment variable, a new status) must be made three times; one copy that is forgotten silently stops testing it.
- **Recommended fix:** one support module for the helpers; the tests stay where they are (no test removed or renamed).
- **Status:** Fixed. `tests/scripts/gateway_run_support.py` (`CheckScript`) holds the fakes, the host and container set-ups and the runner; the three files alias it and keep every test: 16 + 15 + 15 = 46 collected before and after, 46 passed. With the dispatch no longer compiling first, 16 of them fail.

### AUD-093 — Low — Docs/Test — `gateway-run.sh` and its structural test do not know `model-check.sh`
- **Location:** `fabric/lib/gateway-run.sh:2`, `tests/scripts/test_history_check_script.py:141-150`
- **Description:** the header says the library is shared by `gateway-check.sh`, `history-check.sh` and `spike-latency.sh`; `model-check.sh` is a fourth user. The structural test is named "the three scripts" and loops over the same three.
- **Evidence:** `grep -n "model-check" fabric/lib/gateway-run.sh tests/scripts/test_history_check_script.py` finds nothing; `fabric/model-check.sh` sources the library.
- **Root cause:** l07 added a user without updating the places that list the users.
- **Impact:** a reader looking for who depends on the library misses one; a fifth copy of the dispatch in `model-check.sh` would not fail the shared test (it would fail the model test only).
- **Recommended fix:** header lists the four scripts; the shared test covers `model-check.sh` too and is named for what it checks.
- **Status:** Fixed. Header updated; the test is now `test_the_check_scripts_share_one_dispatch` (renamed, not weakened: it gained `model-check.sh` and the requirement that the library names each script). A header without `model-check.sh` and a `host_can_run()` copy in `model-check.sh` both turn it red.

### AUD-094 — Low — Test — `history-check` turns any wrong reply into an empty history
- **Location:** `ledger-gateway/src/history-check.ts:83-86` (`history`), `:136` (`emptyRecords.length === 0`)
- **Description:** `history()` returns `[]` when the reply is not a JSON array. The check "an unknown case has no record" compares the length of that list with 0, so a reply that is `null`, an object or a string passes it.
- **Evidence:** read-through: `Array.isArray(parsed) ? ... : []`. The chaincode Jest test asserts the exact string `"[]"`, so only the chain between peer and probe is not covered.
- **Root cause:** a defensive default written for the type checker, in the one place that exists to catch a wrong answer.
- **Impact:** low (the other checks fail on a wrong type: the 7-record and other-case checks need arrays), but the empty-case check cannot fail for the reason it is there for.
- **Recommended fix:** throw when the reply is not an array, so the probe exits 1 with the message.
- **Status:** Fixed. `history()` throws "GetCaseHistory did not return a list". Compiled in the pinned image; live `history-check.sh` exit 0 twice with `emptyCaseCount` 0. **Could not verify** the failure branch: it needs a chaincode that answers with something other than a list, and none exists to drive it.

### AUD-095 — Info — API/Docs — `INTEGRITY` is a code of the chaincode that IF-10 and the gateway do not know
- **Location:** `chaincode/provenance/src/errors.ts:7`; `ledger-gateway/src/errors.ts:16-22`; Architecture IF-10
- **Description:** l06 added `INTEGRITY` for a ledger state that cannot be read back. The gateway has no status for it (502 `UNAVAILABLE`, cause on stderr, tested) and IF-10 lists four codes. Same family as AUD-082 and AUD-084.
- **Recommended fix:** with the AUD-082 / AUD-084 decision: `INTEGRITY` → 500 or 502 with its own code in IF-09, and IF-10 amended.
- **Status:** Deferred (spec owner)

### AUD-096 — Info — Tooling — `npm run lint` of AGENTS.md does not exist in the Node packages
- **Location:** `AGENTS.md` (Commandes), `chaincode/provenance/package.json`, `ledger-gateway/package.json`
- **Description:** AGENTS.md lists `npm run lint` for the frontend, the gateway and the chaincode. The two packages have no `lint` script and no ESLint configuration; the type check (`tsc --noEmit`, in `npm test`) is the only static check. No `.github/` workflow exists yet (T1.2, B).
- **Impact:** the documented command fails with "Missing script"; style drift is unchecked.
- **Recommended fix:** ESLint is in TRD §18 since round 2: add it with a configuration in both packages when the CI of T1.2 is written, and fix what it finds in one change. Not done here: it adds dependencies and lockfile churn to two packages and belongs with the CI.
- **Status:** Deferred

### AUD-097 — Info — Data — `framework` is the one free-text field of the MODEL record
- **Location:** `chaincode/provenance/src/model.ts:43-49`
- **Description:** 1 to 40 UTF-16 units of any character, control characters and newlines included. The schema says "≤ 40" and `schema.sql` `length(framework) <= 40` counts code points, so a string of 21 emoji is 42 units here and 21 characters there. The same field is already in PROGRESS.md "Trouvé, non construit" for NFR-03.
- **Recommended fix:** with the NFR-03 reading of T2.9: a closed pattern for `framework` (for example `^[A-Za-z0-9 ._+-]{1,40}$`) in the schema, the chaincode and `schema.sql` together. Changing the on-chain schema is a "stop and ask" case of AGENTS.md.
- **Status:** Deferred (spec owner)

### AUD-098 — Info — Docs — the plan says the chaincode sequence increases with l07; the implementation and its tests say it does not
- **Location:** `docs/specs/08-implementation-plan-L.md` §l07 ("Mis à jour : test de déploiement (la séquence du chaincode augmente)"), `tests/scripts/test_deploy_chaincode_script.py`
- **Description:** the chaincode package is a CCAAS connection file; its identifier does not depend on the source, so adding transactions needs no new definition. PROGRESS.md records the decision and two tests pin it (one definition in approve and commit; the package holds no source; the services are recreated after deployment). The plan sentence is now wrong.
- **Recommended fix:** a documentation patch to the plan (version, date, headers, CHANGELOG, as AGENTS.md requires): "le test de déploiement vérifie que la définition ne change pas". A spec change the team owns.
- **Status:** Deferred (spec owner)

## 5. Fix plan

AUD-091 first (the only one with a behavioural risk), then AUD-094, AUD-093, AUD-092. AUD-095 to AUD-098 are decisions or spec changes: recorded, not built.

## 6. Verification and re-audit

Run after the fixes, same commands as the baseline:

| Check | Baseline | After |
|---|---|---|
| `bash scripts/test-l.sh` | exit 0; Python 147 passed / 1 skipped; Jest 183 (chaincode) and 105 (gateway) | exit 0; Python **147 passed / 1 skipped**; Jest **183** and **118** (4 suites) |
| `ruff check .`, `ruff format --check .`, `mypy tests` | pass, 63 files, 20 files | pass, 68 files, 21 files |
| `bash -n` on the five scripts, `git diff --check`, trailing blanks in the new files | pass | pass |
| `npm audit` (both packages) | 0 | not rerun: no dependency or lockfile changed |
| Fabric, targeted (fresh `saam-medtrace` network, started and stopped by the run) | not run | `fabric/gateway-check.sh`, `history-check.sh`, `model-check.sh` exit 0; `history-check.sh` and `model-check.sh` a second time on the same network, exit 0. Output matched what `tests/fabric/test_case_history.py`, `test_gateway_artifacts.py` and `test_model_registry.py` assert (7 records in order; `forged` 400 `SCHEMA`; `DUPLICATE`, `FORBIDDEN` for `verifier` and an agent, `SCHEMA` for an extra field, `NOT_FOUND`). The checks ran in the pinned Node 20 image (the host has no Node). No wallet, runtime directory or `saam-medtrace` container is left. |

**Do the 183 chaincode tests catch a change to MODEL?** 16 source mutations of `model.ts`, `provenance.ts` and `artifact.ts` were run through the whole chaincode suite in the pinned image: 15 failed at least one test (the role check made loose or by prefix, the duplicate check removed, name and framework bounds off by one, unknown fields accepted, `GetModel` without validation, `registeredBy` from the wrong source, `registeredAt` from the wall clock, an absent model reported as `SCHEMA`, key attributes swapped, the role check placed after the schema, a version pattern and a `sha256` pattern without their anchor). One survived: removing the "missing field" loop. It is equivalent: a missing field reaches `requireString` and is refused as `SCHEMA` all the same, which is the owner's own note ("la quinzième est équivalente"). This confirms the 95 l07 tests. The l06 tests were not mutated again: the l06 code review recorded 9 mutations of `provenance.ts`, all red.

**Re-audit of what the audit changed** (`fabric-client.ts`, `history-check.ts`, `gateway-run.sh`, `wallet-fixture.ts`, `ledger-session.test.ts`, `fabric-client.test.ts`, `gateway_run_support.py` and the three script tests): read again after the fixes, compiled and run. No new finding. Two things noticed and kept as they are: the fake `npm` and `docker` now log `|scenario=` for the history and model tests too (harmless: their assertions look for `run build`, `run check:…` and ` -e `); the mock of `connect` returns `Buffer`, as the real client returns a `Uint8Array`, and `submit` and `evaluate` wrap both in `Buffer.from`.

## 7. Unresolved

| ID | Status | Reason | Risk of leaving it | Needed to resolve |
|---|---|---|---|---|
| AUD-095 | Deferred | A public code for `INTEGRITY` is an IF-09 / IF-10 change (with AUD-082 and AUD-084 of round 5) | The gateway answers 502 `UNAVAILABLE` and logs the cause on stderr, so l08 must not map it by accident | Decision of the spec owner; then `errors.ts`, IF-10 and one gateway test |
| AUD-096 | Deferred | ESLint and its CI belong to T1.2 (B) and add dependencies to two packages | `npm run lint` of AGENTS.md fails with "Missing script"; style drift is unchecked | ESLint configuration in both packages when the CI is written |
| AUD-097 | Deferred | A pattern for `framework` changes the on-chain schema and `schema.sql` (AGENTS.md: stop and ask) | Control characters and a UTF-16 length that differs from Postgres for non-BMP text | NFR-03 reading of T2.9, then schema, chaincode and `schema.sql` together |
| AUD-098 | Deferred | A plan patch needs the version, date, header and CHANGELOG steps of AGENTS.md | A reader expects a new sequence number after l07 and finds none | Owner patches `08-implementation-plan-L.md` §l07 |

Could not verify: the full Fabric suite (`scripts/test-l.sh --fabric`, about 50 minutes) was not rerun on the final tree; its tests for l06 and l07 were run through the same three scripts as above, not through pytest. `test_network`, `test_node_fallback`, the WSL2 and native-Linux runs, rootless Docker, a second workstation (A-02.3) and the demo machine were not run, as before.
