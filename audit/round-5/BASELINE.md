# Baseline, round 5 — SAAMSTIAHF

Taken on 2026-11-11 before any round-5 change. State: branch `l04-chaincode-create-get` @ `571e933` (pushed) plus the uncommitted `l05-gateway-artifact-routes` (T2.6, 1/2) working tree: 6 modified tracked files, 11 new files or directories. Host: Windows 11, Git Bash, Docker 29.9.2 (Desktop, running), **Node 22.17.0 on the PATH this time** (the drive that holds it is mounted again; round 4 had none), Python via `py -3` and `uv`.

| Check | Command | Result |
|---|---|---|
| Local suite | `bash scripts/test-l.sh` | exit 0. Python: **86 passed, 1 skipped, 10 deselected** (29.7 s). Jest `chaincode/provenance`: 60 passed. Jest `ledger-gateway`: **11 passed** (2 suites). `tsc --noEmit` clean for both. |
| Gateway on the pinned runtime | `npm ci && npm test && npm audit` in `node:20.20.2-bookworm` (copy of `ledger-gateway`) | Node v20.20.2: **11 passed**. `npm audit`: 6 low, 0 with `--omit=dev`. The host run above used Node 22 only. |
| Python lint / format / types | `ruff check .`, `ruff format --check .`, `mypy tests` | pass / pass (52 files) / pass (13 files) |
| Shell syntax | `bash -n fabric/gateway-check.sh fabric/spike-latency.sh` | pass |
| Dependency scan, gateway | `npm audit` | **6 low**: `deepmerge` ≥ 4.2.0 (GHSA-gcqx-w48m-w2h4) through `jest` → `@jest/core` → `jest-config`, the advisory round 4 worked around in `chaincode/provenance` (AUD-063). `--omit=dev`: 0. |
| Dependency scan, chaincode | `npm audit` | 0 (override from round 4) |
| Fabric suite | not run at baseline | PROGRESS.md records `scripts/test-l.sh --fabric` 10 passed in 1821,86 s for this tree. A live network is started below for the probes. |

Facts recorded for the audit:

- `cookie@2.0.2` (pulled in by `fastify` → `light-my-request`) declares `engines.node >= 22`; the Compose `spike` service and the enrollment build use Node 20.20.2. Jest passed on Node 20.20.2, so the package loads there today.
- `fabric/gateway-check.sh` chooses the host Node whenever `node`, `npm` and `ledger-gateway/dist/gateway-check.js` exist. With Node on this host, the Node 20 branch of that script (container) is not what a green run proves.
