# Audit changes, round 5 — SAAMSTIAHF

Branch `l04-chaincode-create-get` @ `571e933`. **Nothing is committed or staged.** The changes sit in the working tree next to the owner's uncommitted `l05-gateway-artifact-routes` (T2.6, 1/2) files. Findings: `audit/round-5/AUDIT_REPORT.md` (22 findings, AUD-069 to AUD-090; AUD-086 to AUD-090 came from the re-audit of the fixes).

| # | Finding | Files | Change | Verified by |
|---|---|---|---|---|
| 1 | AUD-069 | `ledger-gateway/src/app.ts` | Ajv options `coerceTypes: false`, `useDefaults: false`, `removeAdditional: false`: the closed schema refuses what does not fit. | 10 Jest cases (number, array, `""`, `0`, `false`, `null`) answer 400 with no ledger call; red under `coerceTypes: true` (6 failures) |
| 2 | AUD-070 | `ledger-gateway/src/gateway-check.ts`; `tests/fabric/test_gateway_artifacts.py` | Run-unique artifact id (`gateway-<random>`); the Fabric test runs the check twice on one network. | Live: host run twice and Node 20 container run, exit 0 (before: second run exit 1); Fabric suite 10 passed |
| 3 | AUD-071 | `src/app.ts`, `src/errors.ts`, `src/server.ts`, `src/gateway-check.ts`; `tests/fabric/test_gateway_artifacts.py` | `onFailure` callback for every answer ≥ 500 with `operation`, `status`, one-line `cause` (never body or token); `server.ts` and `gateway-check` write it as a JSON line on stderr; `server.ts` prints a `listening on` line. | 5 Jest cases (cause, create, one line, nothing for caller errors, failing sink); 3 mutations red; live: wrong `CHANNEL_NAME` logs the cause; the Fabric test reads the line for the stopped peer |
| 4 | AUD-072 | `src/fabric-client.ts` | The session map holds the pending creation; a failed creation is dropped; `close()` closes every opened session and later calls are refused. `connectLedger(settings)` takes its settings (default: environment) so tests need no environment. | Live: 5 concurrent reads → 1 client made, 1 closed (before 5 / 1); 5 Jest cases, mutations red |
| 5 | AUD-073 | `src/settings.ts` (new), `fabric-client.ts`, `server.ts`, `gateway-check.ts`, `spike-submit.ts`, `spike-latency.ts`, `.env.example`; `tests/scripts/test_node_packages.py` | `envSetting` treats empty or blank as unset; port must be digits ≤ 65535; `WALLET_DIR` and `PEER_TLS_CERT` commented out in the example. | 4 Jest cases; 2 static tests (no `process.env.X ??` in `src`, only `AGENT_TOKEN_FILE` empty in the example) red under mutation; live `server.js` with empty variables answers 404 for an absent id |
| 6 | AUD-074 | `src/app.ts` | `setNotFoundHandler`: 404 `NOT_FOUND` in the envelope. | 4 Jest cases; red under mutation |
| 7 | AUD-075 | `ledger-gateway/package.json`, `package-lock.json`; `tests/scripts/test_node_packages.py`; `PROGRESS.md` | `overrides: {"deepmerge": "4.1.2"}`, lockfile regenerated in the pinned image (diff: the `deepmerge` entry and `engines`), the guard test runs over both packages, the PROGRESS.md sentence names the right advisory. | `npm audit` 0 (was 6 low); `npm ls deepmerge` shows 4.1.2 overridden |
| 8 | AUD-076 | `ledger-gateway/package.json`; `tests/scripts/test_node_packages.py` | `npm test` removes `dist-test` between type check and test compile. | Reproduced first (stale `ghost.test.js` ran as a third suite); static test over both packages red without the step |
| 9 | AUD-077 | `fabric/gateway-check.sh`; `tests/scripts/test_gateway_check_script.py` (new, 15 tests) | Compiles first in both branches, stops with `environment unavailable` on a build failure; probe functions and a `main` guard so the script can be tested without Docker. Executable bit unchanged. | 15 tests; removing either build step turns 6 tests red; live host and container runs |
| 10 | AUD-078 | `src/errors.ts`; `test/routes.test.ts` | The chaincode code must follow `chaincode response <n>, `. The test double for the read path used the bare form `NOT_FOUND: …`, which no real error has; it now uses the observed form (the test was wrong, its expectation of 404 is unchanged). | 7 mapping cases plus a gRPC `NOT_FOUND`, a code inside other text and an unknown code; 2 failures under mutation |
| 11 | AUD-079 | `test/routes.test.ts`, `test/tokens.test.ts`, `test/fabric-client.test.ts` (new) | Gateway Jest 11 → 97 (91 after the first pass, 97 after the re-audit). One test renamed: "loads a token file without echoing its values" → "loads a token file" (it never checked an echo); the refusal tests now assert that no message holds the token or the path. | Jest 91 passed; 10 of 11 source mutations red, the 11th equivalent |
| 12 | AUD-080 | `ledger-gateway/package.json`, `package-lock.json`; `tests/scripts/test_node_packages.py` | `engines.node >= 20.19.0`. | static test red without it |
| 13 | AUD-081 | `tests/scripts/test_artifact_schema_parity.py` (new, 7 tests) | Gateway and chaincode schemas compared: types and order, fields, required list, patterns, bounds, `offchainRef`. | 6 mutations red |
| 14 | existing test | `tests/scripts/test_node_packages.py` | `test_spike_submit_defaults_work_from_a_host_with_node` looked for `?? "localhost:18051"`; it now looks for `envSetting("PEER_ENDPOINT", "localhost:18051")`. Same intent, same strictness. | local suite |
| 14a | AUD-086 | `src/fabric-client.ts` (`assertEnrolled`), `src/tokens.ts` (`identities()`), `src/server.ts` | Start-up check: every identity of the token file must have `cert.pem`, `key.pem` and `msp-id` in the wallet; the error names identity and file. | 4 Jest tests, mutation red; real `server.js` on Node 20: exit 1 with the message |
| 14b | AUD-087 | `src/fabric-client.ts` | `closed` tested again after the wallet reads, so `close()` during a creation opens no channel. | 1 Jest test, mutation red |
| 14c | AUD-088 | `src/settings.ts` | `envSetting` returns the trimmed value (CRLF `.env`). | 1 Jest test, 3 failures under mutation; real server accepts `GATEWAY_PORT=0<CR>` |
| 14d | AUD-089 | `src/gateway-check.ts` (`server.ts` caught the same slip) | `\n` instead of a raw line break inside a template string. | scan of `src/` and `test/`: none left |
| 14e | AUD-090 | `src/server.ts` | `app.close()` rejection is caught: one line on stderr, exit code 1, then the ledger is closed. | read-through; live start and SIGTERM, exit 0 |
| 15 | tracking | `PROGRESS.md` | T2.6 proof row extended; problems rows for round 5 and for the audit/engines note. | read-through |
| 16 | documentation | `audit/round-5/*` | Baseline, inventory, report, this file. | |

## Not changed, on purpose

- **AUD-082** (commit conflict answered 502) and **AUD-084** (IF-09/IF-10 codes, `@types/jest`): spec changes, Deferred.
- **AUD-083** (30 s race, internal error as 502) and **AUD-085** (50-minute Fabric suite): Won't fix.

## Decisions you may want to review

1. The gateway now refuses every type mismatch with 400 (AUD-069). A client that sent `modelVersion: ""` for "none" must send `null` or omit the key.
2. The 502 body is still the same for every cause; the cause goes to stderr (AUD-071). A different public code for a commit conflict needs your decision (AUD-082).
3. `engines` is `>=20.19.0` (AUD-080); the TRD says "Node 20". Say so in the TRD when the suite version is next bumped.
4. `connectLedger` takes an optional settings argument (AUD-072/073) so that tests can build a wallet in a temp folder.
5. I ran a Fabric network by hand for the probes and stopped it; `fabric/wallet` and `fabric/.runtime` are absent. Docker Desktop is left as the host had it.
6. Temporary files (`/tmp/r5_*`, `$TEMP/r5-*`) are outside the repository.
