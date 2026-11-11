# Audit report, round 3 — SAAMSTIAHF

Date: 2026-11-10 · Scope: the uncommitted `l03-latency-baseline` (T1.8) work on top of `l02-agent-identities` @ `f37e865`. Rounds 1 and 2: `audit/`, `audit/round-2/`. Finding IDs continue from AUD-047.

## 1. Summary

T1.8 adds a seven-transaction latency probe (`ledger-gateway/src/spike-latency.ts`), a wrapper (`fabric/spike-latency.sh`), a test file and the recorded result (p50 = 2,084254 s, p95 = 2,262708 s, `BatchTimeout` kept at `2s`). The measurement logic is sound: the percentile numbers in PROGRESS.md reproduce from the listed samples (nearest rank: rank 4 and rank 7 of 7), the budget comparison is done on integer microseconds, the report carries the fields the plan asks for, and no secret or wallet content is logged.

The defects are in the contract around the measurement: an exit-code collision, a DoD command that does not run on its own, a test that breaks when the very decision it guards is taken, and a wrapper that cannot be tested without Docker.

| Severity | Count | IDs |
|---|---|---|
| Critical / High | 0 | |
| Medium | 2 | AUD-048, AUD-050 |
| Low | 3 | AUD-049, AUD-051, AUD-052 |
| Info | 4 | AUD-053, AUD-054, AUD-055, AUD-056 |

Decisions needed from the user: none. AUD-054 is a git action for the owner (branch name, mode bit).

## 2. Coverage

5 files read in full (3 new, 2 modified); context files listed in `INVENTORY.md`; everything else unchanged since round 2 (`git diff --stat f37e865` shows only the 2 modified files). Nothing excluded beyond round 2.

## 3. Baseline

See `BASELINE.md`: local suite 55 passed / 1 skipped, `tsc --noEmit` clean, ruff and mypy clean except one format failure, `npm audit` 0.

## 4. Findings

### AUD-048 — Medium — Correctness — a failed build exits 2, the code that means "budget exceeded"
- **Location:** `fabric/spike-latency.sh:2-3, 38, 56-62`
- **Description:** the header defines exit 0 = within budget, 2 = measured budget breach, 1 = no baseline. `npm run build` runs under `set -e`, and `npm run` returns the child's status; `tsc` returns 2 on a type error. A broken build therefore leaves the script with exit 2. Any caller that trusts the code (a CI job, a person reading "2 = set BatchTimeout to 0.5 s") is told the budget was breached when nothing was measured. Same for any other status from `docker compose run` or the Node process.
- **Evidence:** old script in a scratch tree with a stub `npm` whose `run build` exits 2 → script exit code 2, no report (`BASELINE.md`). `npm run <script that exits 2>` → exit 2 (checked).
- **Root cause:** the script forwards whatever status the last command returns instead of owning its three-value contract.
- **Fix:** a failed build is `unavailable` (exit 1); after the measuring command only 0 and 2 are passed through, anything else becomes 1 with a message. The script is split into functions with a `main` guard so the contract can be tested.
- **Status:** Fixed. `fabric/spike-latency.sh` rewritten as functions with a `main` guard; a failed build is exit 1, the measuring command's status is passed on only if it is 0 or 2. Verified by `tests/scripts/test_spike_latency_script.py` (red against the old script and under two mutations, green now) and by live runs on both branches.

### AUD-049 — Low — Docs/DX — `npm run spike:latency` (the DoD command) does not run on its own
- **Location:** `ledger-gateway/src/spike-latency.ts:19-20, 83-85`; plan 08 T1.8 and plan L §6 name `npm run spike:latency` as the command.
- **Description:** `BATCH_TIMEOUT` and `ENDORSEMENT_POLICY` are required environment variables that only `fabric/spike-latency.sh` sets. Run as documented, the command stops at once. A missing wallet also surfaces as a raw `ENOENT` instead of the "run `network.sh start` and `enroll-identities.sh`" hint the shell script gives.
- **Evidence:** `cd ledger-gateway && npm run spike:latency` → `environment unavailable: BATCH_TIMEOUT is required` (`BASELINE.md`).
- **Root cause:** the probe delegates reading two repository settings to the wrapper, so it works only through the wrapper.
- **Fix:** when the variables are absent the probe reads the same two settings from `fabric/config/configtx.yaml` and `fabric/scripts/deploy-identity-spike.sh` (host layout); the variables still win, and the wrapper still sets them for the container run where only `/gw` is mounted. A missing wallet gives the hint.
- **Status:** Fixed. `ledger-gateway/src/spike-latency.ts` reads `BatchTimeout` and the policy from the repository files when the variables are absent, and names the missing wallet file. Verified live: `npm run spike:latency` alone gave 7 `VALID`, exit 0; the Fabric test now runs it after the wrapper.

### AUD-050 — Medium — Test — the guard test pins `BatchTimeout` to `2s`
- **Location:** `tests/fabric/test_latency_budget.py:194`
- **Description:** `assert report["batchTimeout"] == "2s"` runs before the budget branch. When p95 exceeds 7,3 s the plan's decision is to set `BatchTimeout` to 0,5 s; after that change the test fails on this line for a reason that has nothing to do with latency, and the l04 re-measurement fails the same way.
- **Root cause:** the expected value is a copy of today's configuration instead of the configuration itself.
- **Fix:** the test reads `BatchTimeout` from `fabric/config/configtx.yaml` and compares the report with it.
- **Status:** Fixed. The test compares with the value read from `configtx.yaml`.

### AUD-051 — Low — Test/Style — format check regression
- **Location:** `tests/fabric/test_latency_budget.py:69-105, 190`
- **Evidence:** `ruff format --check .` → 1 file would be reformatted (round 2 ended with 40 clean).
- **Fix:** `ruff format`.
- **Status:** Fixed. `ruff format` applied; `ruff format --check .` clean (46 files).

### AUD-052 — Low — Test — the wrapper has no test and its Docker path is never exercised
- **Location:** `fabric/spike-latency.sh:36-62`; `tests/fabric/test_latency_budget.py`
- **Description:** the only tests that run the wrapper are the missing-wallet case and the Fabric test, which takes the host-Node branch whenever Node and `node_modules` exist. The container branch (`docker compose … run … spike`) and the exit-code handling are not covered by any test. The script cannot be sourced, so they cannot be tested without a network.
- **Fix:** functions plus a `main` guard (as `scripts/test-l.sh` has); non-Fabric tests replace `npm` and `docker` with shell functions and check both branches, the environment handed to the probe and the exit codes.
- **Status:** Fixed. 19 new non-Fabric tests; both branches also ran against a real network (Windows host branch, Windows container branch, Ubuntu/WSL2 container branch).

### AUD-053 — Info — Test/Architecture — logic exists twice
- **Location:** `ledger-gateway/src/spike-latency.ts:64-80`; `tests/fabric/test_latency_budget.py:18-39`; `ledger-gateway/src/spike-submit.ts:67-77`
- **Description:** nearest-rank percentile and the outcome classification live in the TypeScript probe and again in the test file; the two unit-style tests exercise the test-file copies, so only the Fabric test checks the TypeScript numbers (against an independent oracle, which is the right design). `describe` is duplicated between `spike-submit.ts` and `spike-latency.ts`.
- **Status:** Deferred. The gateway has no unit-test runner yet (same cause as AUD-043); l04 replaces the demo chaincode and T2.6 builds the real gateway with Jest. Revisit there; a shared `describe` belongs in that module.

### AUD-054 — Info — Process — branch and mode bit
- The T1.8 work sits on `l02-agent-identities`, which is already pushed. AGENTS.md wants one branch named after the increment: `git switch -c l03-latency-baseline` before committing (uncommitted changes travel with the switch).
- `fabric/spike-latency.sh` is executable on disk but untracked; stage it with `git add --chmod=+x fabric/spike-latency.sh` (the host has `core.fileMode=false`; `tests/scripts/test_git_hygiene.py` fails on a tracked `*.sh` that is not 100755).
- **Status:** For the owner; nothing changed by the audit.

### AUD-055 — Info — measurement caveats (recorded, no change)
- The first sample (2,262708 s) includes the TLS connection and gateway warm-up; the other six are 2,03–2,10 s. With seven samples nearest-rank p95 equals the maximum, so the cold start is inside the reported p95 (conservative).
- Each sample ≈ `BatchTimeout` (2 s) + 0,03–0,26 s: a single transaction never fills a batch, so latency is dominated by the timeout. Concurrent anchoring in the real pipeline is out of scope for T1.8.
- `endorsementPolicy` and `batchTimeout` in the report are read from repository files (the deploy script and `configtx.yaml`), not queried from the channel. The endorsers are forced to Org1 + Org2 by `endorsingOrganizations`.
- The recorded run used the host-Node branch on Windows; the container branch and Linux are covered by the verification in `CHANGES.md`.
- The `[TBD: mesure T1.8]` markers in System Design §5/§10/§13 and TRD §8 remain; PLAN 08 T1.8 asks only for the PROGRESS.md entry, and editing the specs means a suite version bump the team should decide.

### AUD-056 — Info — Linux ownership of files written by the container branch
- **Question:** the container branch runs `npm run build` as root inside `/gw` (read-write mount). Does it leave root-owned files, as AUD-046 did?
- **Status:** Closed, no defect. On Ubuntu 22.04/WSL2 (uid 1000, no usable `node`, so the container branch runs) the Fabric latency test passed (`p95` 2,200598 s) and `find . -user root` in the tree returned 0 files afterwards: `dist` already exists, owned by the user, from the enrollment build, and the root process rewrites its files in place.

## 5. Fix plan

Done in this order: AUD-048 + AUD-052 (script restructure + tests), AUD-049 (probe defaults), AUD-050, AUD-051, then verification on Windows (local suite, Fabric suite, both branches against a real network) and on Ubuntu/WSL2 (container branch, ownership), then PROGRESS.md.

## 6. Final state

| Check | Baseline | After |
|---|---|---|
| `bash scripts/test-l.sh` | 55 passed, 1 skipped | **74 passed, 1 skipped**, `tsc --noEmit` both packages |
| `bash scripts/test-l.sh --fabric` | not re-run | **9 passed** (924,81 s) |
| `ruff check .` / `ruff format --check .` | pass / **1 file** | pass / pass (46 files) |
| `mypy tests` | pass | pass (11 source files) |
| `npm audit` (ledger-gateway) | 0 | 0 (no dependency changed) |
| `npm run spike:latency` alone | **fails** (`BATCH_TIMEOUT is required`) | 7 `VALID`, exit 0 |
| Failed build, exit code of the wrapper | **2** | 1 |
| Container branch against a real network | never run | Windows: 7 `VALID`; Ubuntu/WSL2: test passed, 0 root-owned files |

Not covered: native Linux Docker Engine and rootless Docker; macOS; a second workstation (A-02.3). The Windows Fabric suite ran before the last test-helper edit (AUD-056 follow-up); the latency test, the only test that edit touches, was re-run afterwards on Windows (passed, 237,76 s) and on Ubuntu/WSL2 (passed, 90,02 s).

Findings: 9 total. Fixed 5 (AUD-048 to AUD-052), Closed 1 (AUD-056), Deferred 1 (AUD-053), Info for the owner 2 (AUD-054, AUD-055).
