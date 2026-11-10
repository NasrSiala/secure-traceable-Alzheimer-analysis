# Baseline, round 4 — SAAMSTIAHF

Taken on 2026-11-10 before any round-4 change. State: branch `l03-latency-baseline` @ `5bd6b88` (pushed) plus the uncommitted `l04-chaincode-create-get` (T2.5a, 1/2) working tree: 14 modified files (one deleted demo chaincode `identity-spike.ts`, one deleted `deploy-identity-spike.sh`), 9 new files. Host: Windows 11, Git Bash, Docker 29.9.2 (Desktop), **Node absent from the PATH** (the drive that holds it is not mounted), Python via `py -3`.

| Check | Command | Result |
|---|---|---|
| Local Python suite | `bash scripts/test-l.sh` (pytest part) | **74 passed, 1 skipped, 9 deselected** (same count as round 3: no Python test was added by l04) |
| TypeScript and Jest | `npm test` in `chaincode/provenance` and `ledger-gateway` (called by `test-l.sh`) | **Not run at baseline**: Docker Desktop stopped while the suite started ("needs Node 20 or a running Docker daemon", exit 3). PROGRESS.md records Jest 6 passed and `tsc --noEmit` clean for this tree, run on a working daemon. |
| Python lint / format / types | `ruff check .`, `ruff format --check .`, `mypy tests` | pass / pass (46 files) / pass (11 files) |
| Shell syntax | `bash -n` on the four changed or new scripts | pass |
| Dependency scan | `npm audit` in the pinned Node image | `ledger-gateway`: 0. `chaincode/provenance`: **6 low** (`deepmerge` ≥ 4.2.0, GHSA-gcqx-w48m-w2h4, reached through `jest` → `@jest/core` → `jest-config`); round 2 ended with 0 for both. The only offered fix is `npm audit fix --force`, which installs jest 25.1.0 (breaking). |
| Fabric suite | not run at baseline | PROGRESS.md records 9 passed in 1000,87 s for this tree |
| Re-run of the latency probe on one network | reasoning from the code, confirmed live below | the probe reuses `latency-1` … `latency-7` as identifiers; `CreateArtifactRecord` refuses an existing `artifactId` (AC-07.3) |

Environment during the audit: Docker Desktop's engine stopped by itself between two commands and its backend hung ("still waiting for init control API", 9 min). I killed the Docker Desktop processes and started it again so that the live checks could run.
