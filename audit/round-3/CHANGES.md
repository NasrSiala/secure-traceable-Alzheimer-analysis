# Audit changes, round 3 — SAAMSTIAHF

Branch `l02-agent-identities` @ `f37e865`. **Nothing is committed or staged.** The changes sit in the working tree next to the owner's uncommitted `l03-latency-baseline` (T1.8) files. Findings: `audit/round-3/AUDIT_REPORT.md`.

| # | Finding | Files | Change | Verified by |
|---|---|---|---|---|
| 1 | AUD-048, AUD-052 | `fabric/spike-latency.sh` | Rewritten as functions (`wallet_present`, `runtime_prepared`, `host_can_run`, `read_settings`, `measure_on_host`, `measure_in_container`, `main`) with a `main` guard, as `scripts/test-l.sh` has. A failed build exits 1 ("environment unavailable: the TypeScript build failed"). After the measuring command only 0 and 2 are passed on; any other status becomes exit 1 with the status in the message. Behaviour otherwise unchanged (same commands, same arguments, same variables). | `tests/scripts/test_spike_latency_script.py` (19 tests, host and container branch): red against the old script; red again under two mutations (build failure ignored, every status passed on); green. Old script reproduced exit 2 on a failing build before the change. |
| 2 | AUD-049 | `ledger-gateway/src/spike-latency.ts` | `BATCH_TIMEOUT` and `ENDORSEMENT_POLICY` still win when set (the wrapper sets them for the container run). When absent, the probe reads `BatchTimeout` from `fabric/config/configtx.yaml` and `POLICY=` from `fabric/scripts/deploy-identity-spike.sh`. A missing wallet file is reported by name with the "start the network, enroll" hint instead of a raw `ENOENT`. | `npm run spike:latency` alone failed before (`BATCH_TIMEOUT is required`); live run after: 7 `VALID`, exit 0. The Fabric test now also runs it alone. Regexes checked on the real files and on a CRLF line. |
| 3 | AUD-050 | `tests/fabric/test_latency_budget.py` | `assert report["batchTimeout"] == "2s"` became a comparison with `BatchTimeout` read from `configtx.yaml` (`configured_batch_timeout()`). New `_assert_probe_runs_on_its_own()` at the end of the Fabric test runs `npm run spike:latency` with the wrapper variables emptied, when the wrapper's own `host_can_run` says the host can. | Fabric latency test: Windows 1 passed (237,76 s), Ubuntu/WSL2 1 passed (90,02 s). The first Linux run failed in this new helper (it tested `shutil.which("npm")`, and WSL has a Windows `npm` on the PATH without a usable `node`); fixed by calling the wrapper's `host_can_run`. |
| 4 | AUD-051 | `tests/fabric/test_latency_budget.py` | `ruff format`. | `ruff format --check .`: 46 files clean |
| 5 | tracking | `PROGRESS.md` | T1.8 row: post-audit proof, control measurements; decision row: control measurements; state lines: date, audit round 3, `git switch -c l03-latency-baseline` and `git add --chmod=+x` reminder; problems: round-3 row. | read-through |
| 6 | documentation | `audit/round-3/*` | Baseline, inventory, report, this file. | |

## Not changed, on purpose

- **AUD-053** (percentile math and `describe` exist twice; the unit-style tests cover the test-file copies): Deferred to the gateway module of T2.6 / l04, where a unit-test runner exists. The Fabric test checks the TypeScript numbers against an independent oracle.
- **AUD-054**: branch name and mode bit are git actions for the owner.
- **AUD-055**: measurement caveats recorded; the `[TBD: mesure T1.8]` markers in the specs are left for the team (editing them is a suite version bump).

## Decisions you may want to review

1. The probe reads two repository files when started alone. The shell wrapper still parses the same two settings for the container run, so the parsing exists twice (shell and TypeScript); the container mounts only `ledger-gateway`, so one side cannot read the other's files without widening the mount (round-2 AUD-035 narrowed it).
2. `fabric/spike-latency.sh` now refuses to forward statuses other than 0 and 2. A budget breach is still exit 2.
3. Docker Desktop was not running when the live checks began; I started it (`Docker Desktop.exe`) and left it running.
4. Temporary files (`/tmp/r3_*`, scratch trees) are outside the repository.
