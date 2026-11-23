# Codebase Audit Report — SAAMSTIAHF

Date: 2026-11-19 · Branch: `l12-sha256-padder-multiblock` @ `b2e2b3b` plus uncommitted fixes · Auditor: codebase-audit skill

Round 12 is this folder. Earlier rounds are unchanged.

## 1. Executive summary

No Critical or High defect in the chaincode, gateway, Fabric scripts, or Zybo bring-up that were read. Two Medium gaps were confirmed in the source and fixed: a single-record read returned corrupt ledger bytes, and an unknown `/ledger` path answered 404 with no token. Docker was not up, so nothing that needs the engine was run.

| Severity | Found | Fixed | Workaround | Deferred | Won't fix | Could not verify |
|---|---|---|---|---|---|---|
| Critical | 0 | 0 | 0 | 0 | 0 | 0 |
| High | 0 | 0 | 0 | 0 | 0 | 0 |
| Medium | 2 | 2 | 0 | 0 | 0 | 0 |
| Low | 4 | 0 | 0 | 1 | 3 | 0 |
| Info | 2 | 0 | 0 | 0 | 2 | 0 |

## 2. Scope and coverage

Read in full by the review passes, then the cited lines were re-read here before a finding was kept: `chaincode/provenance` source and tests (12 files), `ledger-gateway` source and tests (22 files), Fabric scripts plus integrity tests (27 files), bring-up and `sha256_core_tb.vhd` (16 files). Specs, `tests/scripts` other than `test_bringup_config.py`, and prior `audit/` rounds were not re-read. Lockfiles and the slide deck are excluded.

## 3. Baseline

The local pytest run was aborted before it printed a summary. It is not a failing test. After the fixes: chaincode `npm test` 185 passed; gateway `npm test` 214 passed. Docker did not answer (`docker version` hung), so Fabric was not started.

## 4. Findings

### AUD-125 — GetArtifactRecord and GetModel returned corrupt state

- **Severity:** Medium
- **Category:** Correctness
- **Location:** `chaincode/provenance/src/provenance.ts` (`GetArtifactRecord`, `GetModel`)
- **Description:** History and parent checks parse the stored record and fail with `INTEGRITY`. The two single reads returned the raw bytes, including `not json`.
- **Evidence:** `parseStoredArtifact` is used by history. The single reads returned `Buffer.from(stored).toString("utf8")` with no parse. New tests put `not json` and expect `INTEGRITY`.
- **Root cause:** The read path treated ledger bytes as already valid because only this chaincode writes them.
- **Impact:** A tampered key is handed to the gateway as if it were a record.
- **Recommended fix:** Parse before returning. Keep the stored bytes when the parse succeeds.
- **Status:** Fixed
- **Fix applied:** `parseStoredArtifact` on artifact read, `parseStoredModel` on model read. Chaincode Jest 185 passed.

### AUD-126 — an unknown /ledger path skipped the token

- **Severity:** Medium
- **Category:** Security
- **Location:** `ledger-gateway/src/app.ts` (`setNotFoundHandler`, hook only inside the `/ledger` plugin)
- **Description:** The token hook runs on registered routes. A path with no route used the app 404 handler and answered `NOT_FOUND` with no token.
- **Evidence:** `routes.addHook("onRequest", ...)` is inside `app.register(..., { prefix: "/ledger" })`. The 404 handler was on the root app. A new test calls `GET /ledger/nope` with no token.
- **Root cause:** Fastify does not run a plugin hook for a URL that matches no route in that plugin.
- **Impact:** An unknown ledger URL confirmed that the gateway is there without a token. Registered routes still required one.
- **Recommended fix:** On a `/ledger` miss, require the token before 404.
- **Status:** Fixed
- **Fix applied:** `setNotFoundHandler` checks the token for `/ledger` and `/ledger/*`. `/health` without a token stays 404. Gateway Jest 214 passed.

### AUD-127 — the 30s deadline does not cancel the Fabric call

- **Severity:** Low
- **Category:** Correctness
- **Location:** `ledger-gateway/src/fabric-client.ts` (`withDeadline`)
- **Description:** `Promise.race` stops the HTTP handler. The submit or evaluate keeps running.
- **Evidence:** `withDeadline` clears the timer and does not pass a gRPC deadline into `connect`.
- **Root cause:** The timeout is local to the promise, not to the Gateway client.
- **Impact:** After 502, a submit can still commit. A retry with the same id is `DUPLICATE`.
- **Recommended fix:** Pass Fabric Gateway deadlines (`endorseTimeout`, `commitTimeout`) and close the proposal on timeout. Not done in this round: it changes the client contract and was not simulated against a peer.
- **Status:** Deferred

### AUD-128 — chmod 600 failures are ignored

- **Severity:** Low
- **Category:** Security
- **Location:** `fabric/enroll-identities.sh`, `fabric/scripts/enroll-identities.sh`
- **Description:** `chmod 600 ... || true` continues when the mode cannot be set.
- **Evidence:** The `|| true` is on `identities.env`, `cc.env`, and wallet key files.
- **Root cause:** On some Windows bind mounts `chmod` fails. Earlier rounds kept the enrollment working there.
- **Impact:** A failed chmod can leave a key readable by others. The files are under gitignored `.runtime` and `wallet`.
- **Recommended fix:** Keep the best-effort chmod. Failing the script on Windows would break the known host.
- **Status:** Won't fix

### AUD-129 — bring-up command and AXI offsets

- **Severity:** Low
- **Category:** Correctness
- **Location:** `hw/ps_app/bringup/hello.c` (H and R look at `line[0]` only); `hw/rtl/axil_reg_bringup.vhd` (non-zero word offsets still return OK)
- **Description:** `Hfoo` is treated as help. A write off the register address gets `bresp` OK and changes nothing.
- **Evidence:** The command switch uses `line[0]`. The VHDL comment says higher offsets are ignored, and `bvalid` is still asserted with OK.
- **Root cause:** The bring-up console and slave are minimal. Round 9 already simulated the AXI slave.
- **Impact:** Only the spike console and the test register, not the SHA-256 core.
- **Recommended fix:** Leave the spike. The product UART protocol is IF-14, not this console.
- **Status:** Won't fix

### AUD-130 — gateway HTTP and the serve-script mount

- **Severity:** Info
- **Category:** Config
- **Location:** `ledger-gateway/src/server.ts`; `fabric/gateway-serve.sh`
- **Description:** The process speaks HTTP. `GATEWAY_SERVE_TOKEN_DIR` is bind-mounted read-only after a check that `tokens.json` exists.
- **Evidence:** Default host is `127.0.0.1`. The mount is `-v "${token_dir}:/tokens:ro"`. The variable is set by the test, not by an HTTP client.
- **Root cause:** TLS is left to a reverse proxy. The serve script is a test harness.
- **Impact:** A non-loopback bind without TLS would expose `X-Agent-Token`. The default does not.
- **Recommended fix:** Keep the default on localhost.
- **Status:** Won't fix

### AUD-131 — Docker was not available

- **Severity:** Info
- **Category:** Test
- **Location:** host Docker engine
- **Description:** `docker version` did not return.
- **Evidence:** The command hung and was aborted. No `saam-medtrace` container was started.
- **Root cause:** Docker Desktop was still starting.
- **Impact:** Fabric integration was not re-run. The Jest suites do not need it.
- **Recommended fix:** Re-run `scripts/test-l.sh --fabric` when the engine answers.
- **Status:** Could not verify

## 5. Fix plan

1. AUD-125 and AUD-126. Done.
2. AUD-127 stays until a peer is up.
3. AUD-128 through AUD-130 stay as recorded.

No decision is required to keep the fixes. AUD-127 needs a peer before the Gateway deadline change.

## 6. Verification

| Check | Before | After |
|---|---|---|
| Chaincode `npm test` | not run this round (last recorded 183) | 185 passed |
| Gateway `npm test` | not run this round (last recorded 212) | 214 passed |
| Local pytest | aborted, no summary | not re-run |
| Fabric | not run | not run (AUD-131) |

Regressions: none in the two Jest suites.

## 7. Unresolved

| ID | Status | Why | Risk | Next step |
|---|---|---|---|---|
| AUD-127 | Deferred | Needs a live peer to prove cancel-on-timeout | A late commit after 502 | Set Gateway deadlines and test on `saam-medtrace` |
| AUD-128 | Won't fix | `chmod` fails on some Windows mounts | Key mode if chmod fails | Leave it |
| AUD-129 | Won't fix | Bring-up spike, not the product core | Odd console lines, ignored AXI offsets | Leave it |
| AUD-130 | Won't fix | Localhost HTTP is the test default | Token on the wire if bound off-host | Keep the default |
| AUD-131 | Could not verify | Engine did not answer | Fabric regressions unseen | `scripts/test-l.sh --fabric` when Docker is up |

## 8. Re-audit

Re-read `GetArtifactRecord`, `GetModel`, `parseStoredModel`, and `setNotFoundHandler` after the edit. A valid stored artifact is still returned as the original bytes. `/health` without a token is still 404. No new finding.
