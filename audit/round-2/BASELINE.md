# Baseline, round 2 — SAAMSTIAHF

Taken on 2026-11-09 before any round-2 change. State: branch `l01-fabric-network` @ `8f475d4` plus the uncommitted `l02-agent-identities` (T1.4) working tree. Host: Windows 11, Git Bash, Docker 29.9.2 (Desktop), Python 3.10 (`py -3` → 3.14 for pytest/ruff), **no Node on the host**.

| Check | Command | Result |
|---|---|---|
| Local test suite | `bash scripts/test-l.sh` | **19 passed, 1 skipped, 4 deselected** (21 s). The skip is the POSIX-only permission test. |
| TypeScript tests on the host | `npm test` in `chaincode/provenance`, `ledger-gateway` (called by `test-l.sh`) | **Not run**: "node is not on PATH … was not run on the host", exit 0 (see AUD-038) |
| Fabric suite | `bash scripts/test-l.sh --fabric` | **4 passed**, 20 deselected, 617 s (identities + 3 start/stop cycles). Local part again 19 passed / 1 skipped. Exit 0. |
| Python lint | `ruff check .` | pass |
| Python format | `ruff format --check .` | **FAIL**: 2 files would be reformatted (`tests/fabric/test_identities.py`, `tests/fabric/test_network.py`) — new since round 1 (AUD-037) |
| Python types | `mypy tests` | pass (7 source files) |
| Shell syntax | `bash -n` on the 9 scripts | pass |
| Compose | `docker compose … --profile spike --profile tools config -q` | exit 0 |
| TypeScript build | `npm ci && npx tsc` inside `node:20-bookworm` (run by `fabric/enroll-identities.sh`, part of the Fabric suite) | pass |
| Dependency scan | `npm audit` cannot run on the host (no Node). Both lockfiles were checked against the npm registry bulk advisory API instead (`POST /-/npm/v1/security/advisories/bulk`, package names and versions only). | `chaincode/provenance`: `@grpc/grpc-js 1.8.15` (3 high, 1 moderate, 1 low) and `protobufjs 6.11.6` (5 high, 5 moderate); `ledger-gateway`: `@grpc/grpc-js 1.12.4` (3 high, 1 low). See AUD-030. |
| Python dependency scan | `pip-audit` | not applicable: the repository has no Python dependency manifest yet (AUD-001, round 1) |
| Secret scan | regex scan of 62 tracked and untracked text files | clean (only a banned-marker constant in `tests/scripts/test_git_hygiene.py`) |
| Link and ID cross-checks | `audit/tools/crosscheck.py`, `idcheck.py` | same as round 1: 1 false positive (percent-encoded link to `Projet 1.md`), no new orphan ID |
| Production build / app start | n/a | no application code yet; the Fabric network starts and stops (covered by the Fabric suite) |

Pre-existing at baseline: nothing red except the format check (new since round 1) and the skipped host TypeScript tests.

Environment change during the audit: Node 22.17.0 (`/e/MSI.Apps/nodejs`) became available on the host PATH after the baseline was taken. From then on `scripts/test-l.sh` ran `npm test` on the host and failed (AUD-044). The "after" figures in `AUDIT_REPORT.md` §6 are with Node present; `npm audit` was only possible from that point.
