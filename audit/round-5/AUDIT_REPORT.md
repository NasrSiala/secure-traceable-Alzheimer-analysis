# Audit report, round 5 — SAAMSTIAHF

Date: 2026-11-11 · Scope: the uncommitted `l05-gateway-artifact-routes` (T2.6, 1/2) work on top of `l04-chaincode-create-get` @ `571e933`. Earlier rounds: `audit/`, `audit/round-2/`, `audit/round-3/`, `audit/round-4/`. Finding IDs continue from AUD-068.

## 1. Summary

l05 adds the Fastify gateway: `POST /ledger/artifacts` and `GET /ledger/artifacts/{id}` (`app.ts`), `X-Agent-Token` to wallet identity (`tokens.ts`), one Fabric session per identity (`fabric-client.ts`), the normalized error envelope (`errors.ts`), a server entry point, a create/read/duplicate/stopped-peer check (`gateway-check.ts`, `fabric/gateway-check.sh`), Jest tests (11) and a Fabric test. It matches TRD §8.2, IF-09 and plan l05 for the two routes: 401, 400, 403, 404, 409, 422 and 502 are mapped, a token selects the identity, an unknown field is refused without echo. Routes `GET /ledger/cases/{caseId}`, `POST /ledger/models` and `GET /ledger/models/...` are l08 by plan and are not findings.

No defect was found in the authentication path (constant-time compare, identity name checked against a closed pattern and the wallet root, no token in any response or file). The defects sit in the validation layer, the probe and the operating edges: the request validator silently rewrites input, the check script works once per network, failures leave no trace, and several defaults break when a variable is set but empty.

| Severity | Count | IDs |
|---|---|---|
| Critical / High | 0 | |
| Medium | 3 | AUD-069, AUD-070, AUD-071 |
| Low | 13 | AUD-072, AUD-073, AUD-074, AUD-075, AUD-076, AUD-077, AUD-078, AUD-079, AUD-080, AUD-086, AUD-087, AUD-088, AUD-090 |
| Info | 6 | AUD-081, AUD-082, AUD-083, AUD-084, AUD-085, AUD-089 |

AUD-086 to AUD-090 were found by the re-audit of the fixes (section 6), not by the first pass.

Decisions needed from the user: none blocking. AUD-082 and AUD-084 are spec changes (new error code for a commit conflict; IF-09 code list; `@types/jest`) for you or B.

## 2. Coverage

All 17 changed or new files read in full except the 4495-line lockfile (versions, `npm audit` and `npm ci` consistency checked); the 12 files the audit then changed or added were read again after the fixes (re-audit, section 6.2), one line per file in `INVENTORY.md`. Nothing else differs from `571e933`.

## 3. Baseline

See `BASELINE.md`: Python suite 86 passed / 1 skipped, Jest 60 (chaincode) and 11 (gateway, also on the pinned Node 20.20.2 image), ruff, format and mypy clean, `ledger-gateway` `npm audit` **6 low** (the AUD-063 advisory again), `chaincode/provenance` 0. The Fabric suite was not run at baseline; PROGRESS.md records 10 passed in 1821,86 s for this tree. A live network was started to run the probes below.

## 4. Findings

### AUD-069 — Medium — API/Correctness — the request validator rewrites the body instead of refusing it
- **Location:** `ledger-gateway/src/app.ts:98` (`ajv: { customOptions: { removeAdditional: false } }`), `app.ts:20-59` (schema)
- **Description:** Fastify's Ajv defaults are `coerceTypes: "array"` and `useDefaults: true`. Only `removeAdditional` was overridden, so the gateway coerces types before the chaincode sees them. A closed schema (NFR-03) is meant to refuse bad input, not repair it.
- **Evidence:** against the compiled app with a recording ledger (`/tmp/r5_probe.js`): `softwareVersion: 123` reached the ledger as `"123"`; `softwareVersion: ["0.1.0"]` as `"0.1.0"`; `modelVersion: ""`, `0` and `false` as `null`; `parentArtifactId: ""` as `null`; `sha256: ["ab…"]` as a string. All answered 200.
- **Root cause:** the validator options were set for one concern (unknown fields) and left at framework defaults for the others.
- **Impact:** a client bug is stored as a different, valid-looking record. `parentArtifactId: ""` becomes a root artifact, which is the case l06's "an `original` has no parent, every other type needs one" rule exists to catch. The stored record is not what the caller sent, and the caller cannot tell.
- **Recommended fix:** `coerceTypes: false`, `useDefaults: false`, `removeAdditional: false`; tests that each case returns 400 and the ledger is not called.
- **Status:** Fixed. `app.ts` sets `coerceTypes: false`, `useDefaults: false`, `removeAdditional: false`. 10 Jest cases (a number, an array, `""`, `0`, `false`, `null` where a string is required) answer 400 and never reach the ledger; red under mutation (`coerceTypes: true`: 6 failures). `useDefaults: false` is defensive: the schema declares no defaults, so no test can tell it apart.

### AUD-070 — Medium — Test/Correctness — `gateway-check` works once per network
- **Location:** `ledger-gateway/src/gateway-check.ts:34` (`probeArtifact("gateway-probe")`), `:87` (`created.status === 200`)
- **Description:** the artifact identifier is derived from a fixed key. `CreateArtifactRecord` refuses an existing `artifactId` (AC-07.3), so a second run on the same network gets 409 on the first call and exits 1. This is AUD-057 (round 4, latency probe) in the new check.
- **Evidence:** live, host Node: `fabric/gateway-check.sh` run 1 prints `"create":200` and exits 0; run 2 prints `"create":409` and exits 1. Same through the Node 20 container branch (PATH without Node): `"create":409`, exit 1.
- **Root cause:** fixed identifier against a chaincode that is not idempotent; the Fabric test always starts a fresh network, so it cannot see this.
- **Impact:** the check gives a false failure for anyone who re-runs it on a live network (B while writing T2.7, the demo rehearsal).
- **Recommended fix:** a random run identifier in the key, as `spike-latency.ts` does; the Fabric test runs the check twice on one network.
- **Status:** Fixed. The check draws `gateway-<random>` per run. The Fabric test runs it twice on one network. Live: host run twice and the Node 20 container run, all exit 0 (before: second run exit 1).

### AUD-071 — Medium — Config/Operations — every Fabric failure is reduced to one fixed message and nothing is logged
- **Location:** `ledger-gateway/src/app.ts:95` (`logger: false`), `:86-89` (`sendFailure`), `:101-108` (error handler), `errors.ts:55-73`, `server.ts` (no start line)
- **Description:** `chaincodeFailure` maps anything it cannot read to `502 UNAVAILABLE "registre injoignable"` and the cause is dropped; the process writes nothing to stdout or stderr while running.
- **Evidence:** live, calling `fabric-client` directly: a wrong channel gives `14 UNAVAILABLE: failed to get config for channel [nochannel]`, a wrong chaincode name gives `9 FAILED_PRECONDITION: no peers available to evaluate chaincode nocc`, two concurrent creates of one id give `CommitError … status code 11 (MVCC_READ_CONFLICT)`. The gateway answers all three with the same 502 body, and writes no line.
- **Root cause:** the error handler was written for the response and not for the operator.
- **Impact:** a misconfigured channel, a stopped peer, a lost TLS certificate and a commit conflict look identical. FM-03 ("Registre blockchain injoignable") would be raised for a configuration mistake and nobody could tell which.
- **Recommended fix:** `buildApp` takes an `onFailure` callback; `server.ts` writes one JSON line per failure to stderr (operation, status, error class, gRPC code, first line of the message; never the body, never a token) and one line when it listens.
- **Status:** Fixed. `buildApp({ onFailure })`; `server.ts` writes one JSON line per 5xx to stderr (`operation`, `status`, `cause`) and a `listening on` line; `gateway-check` does the same. Live: a wrong `CHANNEL_NAME` now logs `GatewayError code=14: 14 UNAVAILABLE: failed to get config for channel [nochannel]…`. The Fabric test reads that line for the stopped peer. Business answers (400, 401, 403, 404, 409, 422) are not logged.

### AUD-072 — Low — Correctness — concurrent first requests for one identity leak gRPC clients
- **Location:** `ledger-gateway/src/fabric-client.ts:64-84` (`sessionFor`)
- **Description:** `sessionFor` checks the map, awaits three file reads, then stores the session. Two requests that arrive before the first store both build a client and a gateway; the second `set` replaces the first, which `close()` never reaches.
- **Evidence:** live, five `read` calls at once for `agent-ingestion` on a fresh `connectLedger()`: 5 `grpc.Client` objects created, `close()` closed 1, 4 leaked.
- **Root cause:** the cache holds sessions, not the pending creation of a session.
- **Impact:** a pipeline that sends parallel requests after start-up leaks a channel per extra request, each with timers that keep the process alive at shutdown; the first burst after every restart does it.
- **Recommended fix:** cache the promise of the session; drop the entry when creation fails so a later request can retry.
- **Status:** Fixed. `fabric-client.ts` caches the pending session, drops a failed one, refuses requests after `close()`. Live: 5 concurrent reads → 1 client made, 1 closed (before: 5 made, 1 closed). Jest: 5 tests, 2 red under mutation.

### AUD-073 — Low — Config — a variable that is set but empty overrides its default
- **Location:** `fabric-client.ts:51-57`, `server.ts:10-11`, `gateway-check.ts:27`, `spike-submit.ts:24`, `ledger-gateway/.env.example`
- **Description:** every default uses `??`, which only replaces `undefined`. `.env.example` lists `WALLET_DIR=`, `PEER_TLS_CERT=` empty, and a copy loaded with `--env-file` or `env_file:` sets them to `""`.
- **Evidence:** live: `WALLET_DIR= PEER_TLS_CERT= node -e "…connectLedger()"` prints `peer TLS certificate is missing`; `PEER_ENDPOINT=` gives `Could not parse target name ""` at the first call; `Number("")` is `0`, so `GATEWAY_PORT=` listens on a random port.
- **Root cause:** nullish defaults on values that arrive as empty strings; an example file that ships empty optional keys.
- **Impact:** the documented example file does not start the server, and the failure appears at the first request or points at the wrong variable.
- **Recommended fix:** one `setting(name, fallback)` helper that treats empty as unset; optional keys commented out in `.env.example`.
- **Status:** Fixed. `settings.ts` `envSetting` (empty or blank is unset) used by `fabric-client.ts`, `server.ts`, `gateway-check.ts`, `spike-submit.ts`, `spike-latency.ts`; `.env.example` comments out `WALLET_DIR` and `PEER_TLS_CERT`; port must be digits and ≤ 65535. Live: `server.js` with every optional variable set to `""` starts and answers 404 for an absent id; `GATEWAY_PORT=70000` exits 1 with `GATEWAY_PORT is invalid`. Static test over `src/*.ts` and `.env.example`.

### AUD-074 — Low — API — an unknown route or method does not answer in the normalized form
- **Location:** `ledger-gateway/src/app.ts` (no `setNotFoundHandler`)
- **Description:** IF-09 gives one error body for the gateway. Fastify's own 404 body is `{"message":…,"error":"Not Found","statusCode":404}`.
- **Evidence:** `GET /ledger/nope`, `GET /health`, `DELETE /ledger/artifacts` all returned that body (probe above).
- **Root cause:** only the error handler was replaced.
- **Impact:** a client that parses `error.code` gets a second, unrelated shape for a wrong URL.
- **Recommended fix:** a not-found handler returning the envelope with code `NOT_FOUND`.
- **Status:** Fixed. `setNotFoundHandler` answers 404 `NOT_FOUND` "route inconnue" in the envelope; 4 Jest cases (unknown path, `/health`, `DELETE`, the l08 case route that does not exist yet).

### AUD-075 — Low — Dependency — the Jest `deepmerge` advisory is back in `ledger-gateway`
- **Location:** `ledger-gateway/package.json`, `package-lock.json`
- **Description:** l05 added Jest to the gateway; round 4 (AUD-063) worked around GHSA-gcqx-w48m-w2h4 only in `chaincode/provenance`.
- **Evidence:** `npm audit` in the Node 20.20.2 image: 6 low (`deepmerge` through `jest-config`); `--omit=dev`: 0. PROGRESS.md blames `cookie@2.0.2` for the advisory; the advisory is `deepmerge`.
- **Root cause:** the same dev dependency in a second package, without the same override; the guard test covers one package.
- **Impact:** `npm audit` is not 0 for a package whose sibling is; CI with an audit step (TRD §18) would fail.
- **Recommended fix:** same `overrides` pin and lockfile, test over both packages, correct the PROGRESS.md sentence.
- **Status:** Workaround (as AUD-063). `overrides: {"deepmerge": "4.1.2"}`, lockfile regenerated in the pinned image (only the `deepmerge` entry and the `engines` line moved), the test now covers both packages. `npm audit` result in the verification section. The PROGRESS.md sentence is corrected.

### AUD-076 — Low — Test — stale compiled tests are never cleaned in `ledger-gateway`
- **Location:** `ledger-gateway/package.json` (`test`), `jest.config.js`
- **Description:** AUD-061 for the other package: `tsc -p tsconfig.test.json` writes to `dist-test`, Jest runs `dist-test/test/**/*.test.js`, nothing removes a file whose source was renamed or deleted.
- **Evidence:** by the same reproduction as round 4 (a stale `dist-test/test/ghost.test.js` is run by the old sequence).
- **Root cause:** fix applied to one package.
- **Impact:** a deleted test keeps running, or keeps passing.
- **Recommended fix:** same `rmSync` step; a test over both `package.json` files.
- **Status:** Fixed. Same `rmSync('dist-test')` step in the gateway `test` script. Reproduced first: with the old script a stale `dist-test/test/ghost.test.js` ran as a third suite and passed. A static test covers both packages.

### AUD-077 — Low — DX — `fabric/gateway-check.sh` runs whatever `dist/` holds
- **Location:** `fabric/gateway-check.sh:18-29`
- **Description:** unlike `fabric/spike-latency.sh` (builds first, round 3), the script never compiles. After editing `ledger-gateway/src` it checks the old build, in both branches (host and container share the bind-mounted `dist`).
- **Evidence:** reading both scripts; enrollment builds `dist` once, at the time of the Fabric test.
- **Root cause:** pattern copied from `spike-submit.sh`, which predates the build fix.
- **Impact:** a green check that tests code you no longer have.
- **Recommended fix:** `npm run build` before the check in both branches, failing as `environment unavailable`.
- **Status:** Fixed. The script builds first in both branches and stops with `environment unavailable: the TypeScript build failed.` (exit 1); it has a `main` guard and probe functions like `spike-latency.sh`. 15 tests in `tests/scripts/test_gateway_check_script.py` (host and container branches, build failure, check failure, scenario, no wallet, no runtime); removing the build from either branch turns 6 tests red.

### AUD-078 — Low — Correctness — the chaincode code is searched anywhere in the message
- **Location:** `ledger-gateway/src/errors.ts:17`
- **Description:** `\b(PARENT_MISSING|DUPLICATE|FORBIDDEN|NOT_FOUND|SCHEMA):` matches any text. gRPC status names include `NOT_FOUND`; a transport error `5 NOT_FOUND: …` would be returned as 404 `NOT_FOUND` "record absent", and a verification (T3.x) would then report a missing anchor.
- **Evidence:** live, every chaincode failure carries the form `chaincode response 500, <CODE>: <detail>` (duplicate, not found, forbidden, two schema cases). The test double for `read` uses the bare form `NOT_FOUND: …`, which no real error has.
- **Root cause:** a pattern written from the chaincode's `fail()` format, not from what the Gateway client throws.
- **Impact:** low probability (no gRPC `NOT_FOUND` was seen), high cost when it happens: a transport fault reported as a business answer.
- **Recommended fix:** anchor on `chaincode response \d+, `; make the test double use the real form; test that a gRPC `NOT_FOUND` is a 502.
- **Status:** Fixed. The pattern requires the prefix `chaincode response <n>, `. Tests use the real forms (submit: `details[]`; evaluate: `message`) and add a gRPC `5 NOT_FOUND:`, a code inside other text and an unknown code, all answered 502. This changed the test double that sent the bare form `NOT_FOUND: …`, which no real error has (the test was wrong, not weakened: it still expects 404 for an absent record).

### AUD-079 — Low — Test — the route tests leave the validation and mapping branches untested
- **Location:** `ledger-gateway/test/routes.test.ts`, `test/tokens.test.ts`
- **Description:** only one schema case is tested (unknown field). Not covered: malformed `sha256`, `artifactType` outside the list, malformed ids on both routes, `offchainRef` mismatch, a missing required field, body too large, wrong content type, the 403 and 422 and 400 chaincode mappings (`chaincodeFailure` is only reached through DUPLICATE and NOT_FOUND), the not-found shape, a token in the wrong header, the token-file error branches. The test "loads a token file without echoing its values" does not check any echo. Plan l05 lists "forme d'erreur normalisée".
- **Evidence:** reading the two files against `app.ts`, `errors.ts`, `tokens.ts`.
- **Root cause:** tests written for the happy path and the two plan examples.
- **Impact:** the AUD-069 coercion went through all 11 tests.
- **Recommended fix:** add the cases; check by mutation.
- **Status:** Fixed. `routes.test.ts` 7 → 65 tests (validation, coercion, mapping, diagnostics, unknown routes), `tokens.test.ts` 4 → 17, new `fabric-client.test.ts` 9 (gateway Jest: 11 → 91). The test named "loads a token file without echoing its values" asserted no echo; it is now "loads a token file" and the refusal tests assert that no message contains the token or the path. Mutation checks on the gateway sources: 11 mutations, 10 red, 1 equivalent (`useDefaults`).

### AUD-080 — Low — Config — the gateway needs Node ≥ 20.19 and does not say so
- **Location:** `ledger-gateway/package.json` (no `engines`), `package-lock.json` (`node_modules/cookie` 2.0.2: `"type": "module"`, `engines.node >= 22`)
- **Description:** `fastify` → `light-my-request` → `cookie@2.0.2`, an ES-module-only package. The CommonJS gateway loads it through `require(esm)`, available without a flag from Node 20.19 and 22.12. the TRD stack table says "Node 20"; the pinned image is 20.20.2, so it works there.
- **Evidence:** Jest and `gateway-check` ran on Node 20.20.2 and Node 22.17.0; the module type and engines come from the lockfile and the installed `package.json`.
- **Root cause:** a transitive dependency moved to ESM; nothing records the minimum runtime.
- **Impact:** a Node 20.0–20.18 or 18 runtime fails at `require("fastify")` with `ERR_REQUIRE_ESM`, far from the cause.
- **Recommended fix:** `"engines": {"node": ">=20.19.0"}`, a test that pins it, a note in PROGRESS.md.
- **Status:** Fixed. `"engines": {"node": ">=20.19.0"}` in `package.json` and the lockfile; a test pins it. Note: `npm ci` only warns on a mismatch unless `engine-strict` is set.

### AUD-081 — Info — Architecture — ARTIFACT's closed schema now exists twice
- **Location:** `ledger-gateway/src/app.ts:20-59`, `chaincode/provenance/src/artifact.ts`
- **Description:** the gateway repeats the type list, the patterns and the length bounds of the chaincode. Both agree today. If one changes, the other refuses or accepts differently without a test noticing.
- **Recommended fix:** a Python test that compares the two files.
- **Status:** Fixed (as tests). `tests/scripts/test_artifact_schema_parity.py` (7 tests) compares type list and order, field lists, required list, patterns, length bounds and the `offchainRef` rule between the two sources; 6 mutations red.

### AUD-082 — Info — API — two concurrent creates of one id: the loser gets 502, not an answer about the record
- **Location:** `errors.ts` / `fabric-client.ts`
- **Evidence:** live, two `create` calls at once for one id: one succeeds, the other `CommitError … status code 11 (MVCC_READ_CONFLICT)`; the gateway answers 502 "registre injoignable" though Fabric is reachable.
- **Description:** a retry gets `DUPLICATE` (FM-13 handles it: same hash is a success). Mapping the conflict to 409 would be wrong once l06 adds reads of parent keys. IF-09 has no code for "retry".
- **Recommended fix:** a spec decision (new code, for example 409 `CONFLICT` or 503); until then AUD-071's log line names the cause.
- **Status:** Deferred (needs user decision)

### AUD-083 — Info — Correctness — timeouts and internal errors
- **Location:** `fabric-client.ts:34-48` (`withDeadline`), `app.ts:101-108`
- **Description:** the 30 s race does not cancel the call: Fabric Gateway has its own per-step deadlines (5 s evaluate, 15 s endorse, 5 s submit, 60 s commit status), so the call ends, but a submit abandoned at 30 s can still commit and the caller sees 502; a retry gets `DUPLICATE`. An unexpected exception in a handler is also answered 502 "registre injoignable".
- **Status:** Won't fix: bounded by the Gateway's own deadlines and covered by FM-13; IF-09 has no 500.

### AUD-084 — Info — Docs — IF-09/IF-10 and TRD §18 do not list what the code now uses
- **Description:** `UNAUTHORIZED`, `UNAVAILABLE` (gateway-made codes) and `NOT_FOUND` are not in the IF-09 code list; `@types/jest` is not in TRD §18. Extends AUD-064/065.
- **Status:** Deferred (spec change, suite version bump)

### AUD-085 — Info — Test — the Fabric suite takes 30 minutes
- **Description:** PROGRESS.md: 1821,86 s for 10 tests; each Fabric test file starts and stops its own network. A shared network per session would cut it by about two thirds. Not a defect.
- **Status:** Won't fix (not in scope for this increment)

### AUD-086 — Low — Config — a token can name an identity that is not in the wallet
- **Location:** `ledger-gateway/src/server.ts`, `src/tokens.ts` (`loadTokenDirectory`), `src/fabric-client.ts` (`openSession`)
- **Description:** `loadTokenDirectory` checks that an identity name is well formed, not that the wallet holds it. The server starts, accepts the token and fails at that agent's first request.
- **Evidence:** reading `server.ts` and `openSession`: a missing `cert.pem` raises `ENOENT` inside the request, which the gateway answers as 502 "registre injoignable".
- **Root cause:** configuration checked at use, not at start.
- **Impact:** a half-enrolled agent looks like a Fabric outage, hours after the deploy.
- **Recommended fix:** at start-up, check `cert.pem`, `key.pem` and `msp-id` for every identity of the token file and stop with the identity and file named.
- **Status:** Fixed. `assertEnrolled(walletDir, identities)` and `TokenDirectory.identities()`, called by `server.ts` before it connects. 3 + 1 Jest tests; red under mutation.

### AUD-087 — Low — Correctness — `close()` during a session creation leaves a channel nobody closes
- **Location:** `ledger-gateway/src/fabric-client.ts` (`openSession`, after the three wallet reads)
- **Description:** my AUD-072 fix made the creation shared and listed in `opened`, but a creation that was already past the cache check when `close()` ran still built its client afterwards.
- **Evidence:** reading the fix; reproduced by test: `read()` then `close()` at once left one client created.
- **Root cause:** `closed` was tested only on entry.
- **Impact:** a channel with timers that outlives `close()` and keeps the process from exiting at shutdown.
- **Recommended fix:** test `closed` again after the awaits and refuse.
- **Status:** Fixed. 1 Jest test, red under mutation.

### AUD-088 — Low — Config — a value keeps its surrounding blanks
- **Location:** `ledger-gateway/src/settings.ts`
- **Description:** my AUD-073 fix tested the trimmed value for emptiness but returned the original. A `.env` saved with Windows line endings leaves `\r` at the end of every value (`GATEWAY_PORT=8080\r` fails the digits check, `PEER_ENDPOINT` carries a `\r`).
- **Evidence:** reading the code and `listeningPort`.
- **Root cause:** half of a trim.
- **Impact:** the same "the example file does not start" symptom for CRLF files.
- **Recommended fix:** return the trimmed value.
- **Status:** Fixed. 1 Jest test, 3 failures under mutation.

### AUD-089 — Info — Correctness — a template string with a raw line break (introduced by this round)
- **Location:** `ledger-gateway/src/gateway-check.ts:20-22`
- **Description:** my scripted edit wrote the end of `logFailure` as a real line break inside the backticks instead of the two characters `\n`. It worked, but with `autocrlf` a Windows checkout turns the break into CR LF, so the line written to stderr would not be the one the source shows.
- **Evidence:** `grep -n 'failure })}' ledger-gateway/src/*.ts | cat -A` showed the template split over two lines.
- **Root cause:** the escape was consumed by the shell and Python heredoc that produced the edit; the same slip happened once more in `server.ts` and was caught the same way.
- **Recommended fix:** `\n` in the literal; scan the sources for a backtick string that ends on a line break.
- **Status:** Fixed. Scan of `src/` and `test/`: none left.

### AUD-090 — Low — Correctness — a failing `app.close()` was an unhandled rejection
- **Location:** `ledger-gateway/src/server.ts` (`shutdown`)
- **Description:** `void app.close().finally(...)` has no handler for a rejection; Node then ends the process with a stack trace and the ledger channels are closed only by exit.
- **Evidence:** reading `server.ts`.
- **Root cause:** `void` used to silence the lint rule, not to handle the error.
- **Recommended fix:** catch, write one line to stderr, set the exit code, then close the ledger.
- **Status:** Fixed. Entry point only; checked by reading and by the live start/stop run (no unit test: `server.ts` is a `main()` script).

## 5. Fix plan (as executed)

AUD-069 first (data integrity), then AUD-070, AUD-071, AUD-072, AUD-073, AUD-074, AUD-078, AUD-079 in `ledger-gateway/src` with their Jest tests; AUD-075, AUD-076, AUD-080 in `package.json` and the lockfile; AUD-077 in the script; AUD-081 as a Python test. Verify with the local suite, Jest on Node 22 and on the pinned Node 20 image, mutation checks on the new tests, the live network (gateway-check twice, race, empty environment), then `scripts/test-l.sh --fabric`.

## 6. Verification

### 6.1 After the first round of fixes (AUD-069 to AUD-081)

| Check | Before (baseline) | After |
|---|---|---|
| `bash scripts/test-l.sh --fabric`, Python local | 86 passed, 1 skipped | **114 passed, 1 skipped** (+28: 15 gateway-check script, 7 schema parity, 6 package/static) |
| Jest `chaincode/provenance` | 60 passed | 60 passed |
| Jest `ledger-gateway` | 11 passed (Node 22 and Node 20.20.2) | **91 passed** (Node 22.17.0) |
| Fabric suite (Windows) | 10 passed in 1821,86 s (PROGRESS.md) | **10 passed in 2985,18 s** (the gateway test now runs the check twice on one network; the host was also busy) |
| `npm audit` `ledger-gateway` | 6 low (0 with `--omit=dev`) | **0** (0 with `--omit=dev`) |

Live probes on a fresh test network: `fabric/gateway-check.sh` twice in a row (host Node 22) and once through the Node 20.20.2 container branch, all exit 0 with `create:200`; five concurrent first reads: 1 client made, 1 closed; `server.js` with every optional variable set to `""` starts and answers 404 for an absent id; a wrong `CHANNEL_NAME` logs the `UNAVAILABLE … nochannel` cause on stderr; `GATEWAY_PORT=70000` exits 1.

### 6.2 Re-audit of the fixes (AUD-086 to AUD-090) and the two checks left open

The re-audit read every changed file again (`INVENTORY.md`) and found five defects in the fixes themselves (section 4). After fixing them:

| Check | Result |
|---|---|
| `bash scripts/test-l.sh` (this host now has no Node: the pinned image runs both packages) | exit 0. Python **114 passed, 1 skipped**; Jest `chaincode/provenance` 60 passed; Jest `ledger-gateway` **97 passed** (was 91) |
| Jest `ledger-gateway` on the pinned Node 20.20.2 image, run on its own | **97 passed**, `tsc --noEmit` clean, `npm audit` 0. `npm ci` prints `EBADENGINE` for `cookie@2.0.2` (needs Node ≥ 22); the package loads through `require(esm)` and every test passes (AUD-080) |
| Mutation checks of the 6 new Jest tests (in the Node 20 image) | 4 mutations, all red (1, 1, 3, 1 failures) |
| Real `server.js` on Node 20.20.2 Linux, temp wallet, unreachable peer | token naming an identity missing from the wallet: exit 1, `identity agent-features is not enrolled in the wallet (missing cert.pem)`; enrolled identities and `GATEWAY_PORT=0<CR>`: listens, a read answers 502 and stderr carries `GatewayError code=14: 14 UNAVAILABLE: No connection established…`; SIGTERM exits 0 |
| Ubuntu 22.04 under WSL2 (uid 1000, ext4, Docker Desktop engine): local Python suite | 113 passed, 2 failed, 10 deselected: the same two WSL2-only failures as before (`test_check_ports_reports_a_busy_port`, AUD-047, and the nested `test_board_flag_runs_no_board_tests_and_does_not_open_a_device`). All new tests pass there |
| Ubuntu 22.04 under WSL2: `pytest -m fabric tests/fabric/test_gateway_artifacts.py` | **1 passed in 130,36 s** with the code of 6.2 (no Node in the distro, so the container branch of `gateway-check.sh` ran: build, then the flow twice, then the stopped peer). 0 root-owned files in `~/saam`, no `saam-medtrace` container, no `fabric/wallet` afterwards |
| `ruff check .`, `ruff format --check .`, `mypy tests` | pass / pass (58 files) / pass (15 files) |

A measurement trap in `audit/tools/linux_check.sh sh`: a `$(…)` in the command is expanded before the `cd ~/saam`, in the Windows working directory seen through `/mnt/c`, where every file looks root-owned. It first showed 16880 root-owned files; the same `find` run inside the copy shows 0.

**Not re-run after the re-audit fixes:** the full Windows Fabric suite (50 minutes). The code it exercised changed only in `settings.ts` (trim), `fabric-client.ts` (a check after the wallet reads), `tokens.ts` (`identities()`), `server.ts` (not used by the suite) and `gateway-check.ts` (one string); the WSL2 Fabric gateway test, the real-server run and the Jest suite cover those changes.

**Could not verify:** a native Linux Docker Engine and rootless Docker, a second workstation (A-02.3), the machine of the demo (Q-03), and whether the container branch leaves a root-owned `ledger-gateway/dist` on native Linux (under Docker Desktop and WSL2 it does not; same pattern as `spike-latency.sh`).

## 7. Unresolved

| ID | Status | Reason | Risk if left | Needed |
|---|---|---|---|---|
| AUD-075 | Workaround | no patched `deepmerge` exists | none at run time (dev dependency, override pins 4.1.2) | remove the override when upstream fixes or Jest drops it |
| AUD-082 | Deferred | IF-09 has no retry code; mapping a commit conflict to 409 is wrong once l06 reads parent keys | a concurrent duplicate create answers 502 "registre injoignable"; the retry gets `DUPLICATE` (FM-13) | your decision: a new code (409 `CONFLICT` or 503) |
| AUD-083 | Won't fix | Gateway deadlines bound the call; FM-13 covers a retry; IF-09 has no 500 | a 502 for a bug in the gateway | none |
| AUD-084 | Deferred | spec change, suite version bump | spec and code differ on gateway-made codes and on `@types/jest` | you or B: add `UNAUTHORIZED`, `UNAVAILABLE`, `NOT_FOUND` to IF-09/IF-10 and `@types/jest` to TRD §18 |
| AUD-085 | Won't fix | not part of this increment | 50-minute Fabric suite | a shared network fixture, later |
