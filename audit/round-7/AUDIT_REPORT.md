# Audit report, round 7 — SAAMSTIAHF

Date: 2026-11-16 · Scope: the owner's uncommitted `l08-gateway-history-model-routes` (T2.6, 2/2) working tree, on top of the committed and pushed `l07-chaincode-model-registry` @ `5969c89` (which round 6 audited and fixed). Earlier rounds: `audit/`, `audit/round-2/` to `audit/round-6/`. Finding IDs continue from AUD-098.

## 1. Summary

l08 adds the three remaining routes of TRD §8.2 to the gateway: `GET /ledger/cases/{caseId}` (`GetCaseHistory`), `POST /ledger/models` (`RegisterModel`) and `GET /ledger/models/{name}/{version}` (`GetModel`); `buildApp` now takes a `LedgerSession`; the closed MODEL schema is repeated in the gateway and compared with the chaincode's by `tests/scripts/test_model_schema_parity.py`; `fabric/gateway-routes-check.sh` (`npm run check:routes`) drives the five routes on the test network with the real certificates; 79 new Jest tests, 15 contract tests of the script and one Fabric test. It matches TRD §8.2, IF-09 and plan l08: every route is behind the token hook, a refusal by the chaincode keeps its status and its text (`FORBIDDEN` → 403), the gateway does not decide who registers a model (the call goes out under the caller's identity), and no field of the closed schema is taken from the client.

No defect was found in the routes' logic. 17 of 18 mutations of `app.ts` are caught by the Jest suite (the survivor is AUD-100), and the parity test kills 13 of 14 mutations of the two MODEL schemas (the 14th, a gateway body schema that accepts extra properties, is caught by 6 Jest tests). The findings are small: the gateway answers a malformed URL outside the IF-09 envelope (a pre-existing behaviour that the new routes inherit, found by probing), one new test passes with the identity hard-coded, the live check does not look for the real tokens in the replies it checks, a list of users of the shared script library went stale again, and two numbers of PROGRESS.md are wrong.

| Severity | Count | IDs |
|---|---|---|
| Critical / High / Medium | 0 | |
| Low | 5 | AUD-099, AUD-100, AUD-101, AUD-102, AUD-103 |
| Info | 2 new, 4 carried over | AUD-104, AUD-105; AUD-095 to AUD-098 (round 6, unchanged) |

Decisions needed from the user: none blocking. AUD-095 to AUD-098 stay as in round 6 (spec owner or B).

## 2. Coverage

The l07 commits (`7eab37b`, `cee4130`, `5969c89`) were read and fixed in round 6 and did not change since; they are `[=]` in `INVENTORY.md`. The 11 files of the l08 tree (4 modified, 7 new) were read: the 7 new ones in full; `app.ts` in full; `routes.test.ts` (586 lines, only the imports, the fake ledger and the unknown-route list changed) as a diff; `PROGRESS.md` and `package.json` as diffs. One line per file in `INVENTORY.md`. The lockfiles did not change.

## 3. Baseline

See `BASELINE.md`: local suite exit 0 (Python 169 passed / 1 skipped, Jest 183 chaincode and 201 gateway), ruff, format and mypy clean, `npm audit` 0 for both packages. The Fabric suite was not run at baseline (13 tests, about 50 minutes). The probe of odd URLs (same file) is where AUD-099 comes from.

## 4. Findings

### AUD-099 — Low — API — a malformed URL or an over-long path parameter is answered outside the IF-09 envelope
- **Location:** `ledger-gateway/src/app.ts:131-137` (`Fastify({...})` has no `frameworkErrors`); reached by the routes at `:184`, `:204`, `:217`, `:231`, `:242`
- **Description:** the router refuses two kinds of URL before any route, hook or error handler runs: a bad percent-encoding (`%zz`, a lone `%`) and a path parameter longer than 100 characters. Fastify answers them itself: 400 `{"error":"Bad Request","code":"FST_ERR_BAD_URL","message":"'…' is not a valid url component","statusCode":400}` and 414 `FST_ERR_MAX_PARAM_LENGTH`. In both, `error` is a string and `error.code` does not exist. IF-09 says every refusal has the body of TRD §8 (`{"error":{"code","message","details"}}`). l05 fixed the unknown-route 404 the same way (AUD-074), not these two.
- **Evidence:** `audit/round-7/tools/probe-urls.js` on a build of the tree, `app.inject`: `GET /ledger/cases/%zz` → 400 with the shape above; `GET /ledger/models/<101 × m>/1.0.0` → 414; `GET /ledger/models/<100 × m>/1.0.0` → 400 `SCHEMA` (envelope). `ledger-gateway/node_modules/fastify/fastify.js:680-740` shows the `frameworkErrors` option as the only hook for them.
- **Root cause:** the l05 error handler and not-found handler cover what happens after routing; the router's own refusals have their own option, which `buildApp` never set. The l08 routes add two path parameters that a caller composes from free text (`caseId`, model `name`), which makes the case reachable from `LedgerClient` (T2.7, B).
- **Impact:** low today (the pipeline sends well-formed identifiers), but a client that reads `body["error"]["code"]` (`LedgerClient` in T2.7) fails with a type error instead of raising `InvalidRecord` for a name of 101 characters or a name that was not percent-encoded.
- **Recommended fix:** set `frameworkErrors` in `buildApp` so that both answer 400 `SCHEMA` in the envelope; tests for the five routes: a bad percent-encoding and a parameter of 101 characters give the envelope, and the ledger is not called.
- **Status:** Fixed. `buildApp` sets `frameworkErrors`; both cases answer 400 `{"error":{"code":"SCHEMA","message":"requête invalide","details":{}}}`, with or without a token (no route was matched, so no hook ran: the answer tells an unauthenticated caller nothing). 9 new Jest tests (bad percent-encoding on case, model name, model version and artifact routes; 101 characters on all four path parameters); removing the option, answering 414, answering `UNAVAILABLE`, or answering in Fastify's shape each fail those 9. The reply type of the option is generic; `reply as FastifyReply` is a cast to the default type, not a way around a check (the call is the one every other handler makes).

### AUD-100 — Low — Test — the history route test passes when the identity is hard-coded
- **Location:** `ledger-gateway/test/ledger-routes.test.ts:206-210` ("reads with the identity selected by the token")
- **Description:** the only identity the test exercises is `verifier`. A route that calls `ledger.history("verifier", caseId)` whatever the token passes every test.
- **Evidence:** mutation `options.ledger.history(identity, caseId)` → `options.ledger.history("verifier", caseId)` in a copy of the package: `npm test` → all 201 pass (`audit/round-7/tools/mutations-app.json`, #3). The same mutation on `registerModel` (to `"model-admin"`) and on the three `getModel` identities is caught.
- **Root cause:** the registration and lookup tests check three identities each; the history test was written with one.
- **Impact:** a history read would run with the wrong certificate (which the chaincode accepts for everyone, so nothing fails) and the audit trail of who read what would be wrong. NFR-06 asks for the caller's own identity on every call.
- **Recommended fix:** run the test for the three tokens (agent, administrator, verifier) and compare the identity recorded for each.
- **Status:** Fixed. The test is a `test.each` over the three tokens; the verifier case is kept, so nothing was weakened. The three hard-coded-identity mutations of the history route (`"verifier"`, `"agent-ingestion"`, `"model-admin"`) each fail 2 tests (before: all 201 passed).

### AUD-101 — Low — Test — the live routes check looks for one fake token in the replies, not the real ones
- **Location:** `ledger-gateway/src/gateway-routes-check.ts:171`, `:183`
- **Description:** `leaked` is `JSON.stringify(refusals…).includes("not-a-real-token")`. The replies it scans are the refusals of requests made with the real agent, administrator and verifier tokens (403, 409, 404, 400); none of those tokens is looked for. `tokenLeaked: false` in the report therefore says less than it appears to.
- **Evidence:** read-through; the Jest tests do scan the real token (`ledger-routes.test.ts:295`, `:171`), the live script was copied from `gateway-check.ts:141`, where the only token presented in a refusal is the fake one.
- **Root cause:** the check was adapted from a script with one refusal and one token.
- **Impact:** a gateway that echoed the presented token in a 403 would pass the live check. The Jest suite would catch it, but the live check is the one that runs with the real directory of tokens.
- **Recommended fix:** scan for all four tokens (agent, administrator, verifier, unknown).
- **Status:** Fixed. `gateway-routes-check.ts` scans the seven refusal bodies for the agent, administrator, verifier and unknown tokens. Live on a fresh network, twice: exit 0, `tokenLeaked` false. The failure branch was not driven live (it needs a gateway that echoes a token); the Jest tests cover that on the fake ledger.

### AUD-102 — Low — Docs/Test — the list of users of `gateway-run.sh` is stale again and still hand-written
- **Location:** `fabric/lib/gateway-run.sh:2-5`, `tests/scripts/test_history_check_script.py:109-125`
- **Description:** the header names four scripts; `fabric/gateway-routes-check.sh` is a fifth that sources the library. `test_the_check_scripts_share_one_dispatch` loops over the same four names, so a copy of the dispatch in the fifth script would not fail it (the script's own test file has a partial duplicate of the check: `test_gateway_routes_check_script.py:110-122`).
- **Evidence:** `grep -n "gateway-routes-check" fabric/lib/gateway-run.sh tests/scripts/test_history_check_script.py` finds nothing. Same defect as AUD-093 one increment later.
- **Root cause:** AUD-093 added a name to a list; it did not make the list follow the files, so each new check script needs the same two edits.
- **Impact:** low; the next check script will repeat it.
- **Recommended fix:** header lists the five; the test discovers `fabric/*-check.sh` (plus `spike-latency.sh`) instead of naming them, and still requires the known ones so that a rename cannot empty the loop.
- **Status:** Fixed. Header names `gateway-routes-check.sh`; the test globs `*-check.sh`, requires the four known names to be in the result, and for each script (and `spike-latency.sh`) checks that it sources the library, has no copy of the probes, and is named in the library. Four mutations are red: a header without the routes script, a `host_can_run()` copy in it, a new `*-check.sh` with its own dispatch, a new `*-check.sh` that sources the library without being named there.

### AUD-103 — Low — Docs — PROGRESS.md gives the wrong base and the wrong number of new gateway tests
- **Location:** `PROGRESS.md:20` (the T2.6 (2/2) proof row)
- **Description:** "Jest passerelle : 201 passed (105 existants … 96 nouveaux …)". The l07 branch ends with 118 gateway tests (105 plus the 13 of `ledger-session.test.ts`, round 6); the l08 tree adds 83 (79 in `ledger-routes.test.ts`, 4 in `routes.test.ts`). 105 + 96 = 201 hides the error.
- **Evidence:** `BASELINE.md` (per-file counts from `jest --json`: 77, 79, 14, 18, 13 = 201) and the l07 row of the same file ("Jest passerelle 118 passed").
- **Root cause:** the count was taken from a tree that did not have the round-6 test file.
- **Impact:** the proof table of the MR would say 96 new tests where a reviewer counts 83.
- **Recommended fix:** correct the two numbers and add the tests of this audit.
- **Status:** Fixed. The row says 118 existing and 83 new (79 + 4) for the 201 of the owner's run, and records the audit's own result (212).

### AUD-104 — Info — Architecture — `report`, `logFailure` and `codeOf` are copied in the check programs
- **Location:** `ledger-gateway/src/gateway-check.ts:13-26`, `gateway-routes-check.ts:48-61`, `history-check.ts:67`, `model-check.ts:37`, `ledger-gateway/test/ledger-fixtures.ts:50`
- **Description:** each live check program prints a marker line and exit code with its own 5-line `report`; two of them also repeat `logFailure` and `codeOf`, which `test/ledger-fixtures.ts` has a third time.
- **Recommended fix:** one `probe-support.ts` for the programs. Not done: no defect, four programs that run live (about 15 minutes to re-prove), and `ledger-fixtures.ts` is test code that should not import a program helper.
- **Status:** Deferred (owner, with the next check program or T1.2)

### AUD-105 — Info — Test — the eight contract tests of a check script exist in four copies
- **Location:** `tests/scripts/test_gateway_check_script.py`, `test_history_check_script.py`, `test_model_check_script.py`, `test_gateway_routes_check_script.py`
- **Description:** round 6 moved the helpers into `gateway_run_support.py` and kept every test. The tests themselves (compile first, a failed build stops, a failed check fails, no wallet, no runtime, sourcing runs nothing, shared dispatch) are still the same bodies per script; l08 added the fourth copy.
- **Recommended fix:** one parametrized module over the scripts. Not done: it renames or merges existing tests, which AGENTS.md reserves for the owner, and nothing is wrong with them.
- **Status:** Deferred (owner)

### Carried over from round 6, unchanged

AUD-095 (public code for `INTEGRITY`, with AUD-082 and AUD-084), AUD-096 (`npm run lint` does not exist in the Node packages; T1.2), AUD-097 (the free `framework` field, bounded in UTF-16 units by the chaincode and in code points by Ajv and `schema.sql`: the gateway never refuses what the chaincode accepts, so a 21-emoji value gets the chaincode's 400), AUD-098 (plan sentence about the sequence). Deferred (spec owner).

## 5. Fix plan

Order: AUD-099 (code and tests) → AUD-100 (test) → AUD-101 (check program) → AUD-102 (header, test) → AUD-103 (PROGRESS.md, last, with the final counts). AUD-104 and AUD-105 stay open. None needs a user decision.

## 6. Verification and re-audit

| Check | Baseline | After the fixes |
|---|---|---|
| `bash scripts/test-l.sh` | exit 0 | exit 0 (Python 169 passed, 1 skipped; Jest 183 and 212) |
| Jest `ledger-gateway` | 201 passed (5 suites) | **212 passed** (5 suites): `ledger-routes.test` 79 → 90, the others unchanged |
| Jest `chaincode/provenance` | 183 passed | 183 passed (untouched) |
| Python, local suite | 169 passed, 1 skipped | 169 passed, 1 skipped (a test of the suite was changed, none added) |
| `ruff check .`, `ruff format --check .`, `mypy tests` | pass | pass (77 files formatted, 24 files typed) |
| `bash -n` on every `fabric/*.sh`, `fabric/lib/*.sh`, `scripts/*.sh` | pass | pass |
| `tsc --noEmit` | pass | pass |
| `npm audit` (both packages) | 0 | 0 (no dependency changed) |
| `git diff --check` | exit 0 | exit 0 |
| Live, fresh network: `gateway-check.sh`, `history-check.sh`, `model-check.sh`, `gateway-routes-check.sh` twice | not run | exit 0 for all, on one fresh network (`audit/round-7/live.log`): `enroll-identities.sh` 279 s, `gateway-check.sh` 34 s, `history-check.sh` 42 s, `model-check.sh` 30 s, `gateway-routes-check.sh` 46 s then 50 s on the same network (`tokenLeaked` false, `created` 7, `count` 7, 403 / 409 / 404 / 400 / 401 as expected); network stopped, no wallet, runtime or `saam-medtrace` container left |
| Odd URLs (`probe-urls.js`) | Fastify bodies, 400 and 414 | 400 `SCHEMA` in the envelope for every bad percent-encoding and every parameter over 100 characters; the other rows unchanged |

**Mutations.** 18 mutations of `app.ts` run against the owner's tests before any change: 17 killed, 1 survived (AUD-100: the history route with a hard-coded identity). After the fixes: that mutation, with two siblings (`agent-ingestion`, `model-admin`), and four mutations of `frameworkErrors` are all killed. 14 mutations of the two MODEL schemas against `test_model_schema_parity.py`: 13 killed; the survivor (the gateway's body schema accepting extra properties) is killed by 6 Jest tests. 4 mutations of the shared-dispatch test: 4 red. The runners are in `audit/round-7/tools/` (`mutate-gateway.js` with `mutations-app.json` and `mutations-fix.json`, `mutate_parity.py`, `mutate_dispatch.py`).

**Re-audit.** The six files the audit changed were read again as diffs: `app.ts` (one option, one comment, the cast explained), `gateway-routes-check.ts` (a constant and a four-token scan; `UNKNOWN_TOKEN` is the only literal left and is used for the request and the scan), `ledger-routes.test.ts` (two blocks; the test titles keep the `%s` placeholders that Jest fills), `gateway-run.sh` (comment only), `test_history_check_script.py` (the loop gains scripts, loses none), `PROGRESS.md` (two numbers). No new finding.

**Not verified.** The full Fabric suite through pytest (13 tests, about 50 minutes) was not re-run on the final tree; the four live checks above were, on one fresh network, which is the part of it that the changes can touch. Also not run: `test_network`, `test_node_fallback`, the WSL2 and native Linux runs, a second workstation (A-02.3), the demo machine (Q-03). The failure branch of the AUD-101 scan (a gateway that echoes a token) was not driven live: it needs a gateway that does, and the Jest tests cover that case on the fake ledger.

## 7. Unresolved

| ID | Severity | Status | Why | Risk of leaving it | What is needed |
|---|---|---|---|---|---|
| AUD-104 | Info | Deferred (owner) | `report`, `logFailure` and `codeOf` are copied in the check programs; no defect, four live programs to re-prove | A change to the marker or exit convention must be made in four places | A `probe-support.ts` with the next check program, or T1.2 |
| AUD-105 | Info | Deferred (owner) | The eight contract tests of a check script exist in four test files; merging renames tests | Same as above, on the test side | An owner decision to parametrize over the scripts and keep every case |
| AUD-095 | Info | Deferred (spec owner) | Public code for `INTEGRITY`, with AUD-082 and AUD-084 | A server-side ledger fault answers 502 `UNAVAILABLE` | IF-09 and IF-10 amended |
| AUD-096 | Info | Deferred (B, T1.2) | `npm run lint` does not exist in the Node packages | The commands table of AGENTS.md names a command that fails | ESLint and its CI step |
| AUD-097 | Info | Deferred (spec owner) | `framework` is free text bounded in UTF-16 units (chaincode), code points (Ajv, `schema.sql`) | A value of 21 to 40 astral characters passes the gateway and the database but not the chain (400 `SCHEMA` from the chaincode) | A closed pattern: it changes the on-chain schema and `schema.sql` (stop and ask) |
| AUD-098 | Info | Deferred (spec owner) | The plan l07 sentence about the chaincode sequence | A reader expects a sequence bump that never happens | A patch of the plan (version, date, headers, CHANGELOG) |
