# Baseline, round 6 — SAAMSTIAHF

Taken on 2026-11-15 before any round-6 change. State: branch `l06-chaincode-provenance-rules` @ `15dd22e` (pushed) plus the uncommitted `l07-chaincode-model-registry` (T2.5b) working tree: 7 modified tracked files, 7 new files. Host: Windows 11, Git Bash, Docker 29.9.2 (Desktop, running), **no Node on the PATH** (the drive that holds it is not mounted), Python 3.14.7 via `py -3` and `uv`. The TypeScript checks therefore ran in the pinned `node:20.20.2-bookworm` image, the runtime the Compose services use.

| Check | Command | Result |
|---|---|---|
| Local suite | `bash scripts/test-l.sh` | exit 0 in 60 s. Python: **147 passed, 1 skipped, 12 deselected** (29.42 s). Jest `chaincode/provenance`: **183 passed** (2 suites). Jest `ledger-gateway`: **105 passed** (3 suites). `tsc --noEmit` clean for both. |
| Python lint / format / types | `py -3 -m ruff check .`, `py -3 -m ruff format --check .`, `py -3 -m mypy tests` | pass / pass (63 files) / pass (20 files) |
| Shell syntax | `bash -n fabric/model-check.sh fabric/history-check.sh fabric/gateway-check.sh fabric/spike-latency.sh fabric/lib/gateway-run.sh` | pass |
| Whitespace | `git diff --check` | exit 0 (CRLF notices only) |
| Dependency scan, gateway | `npm audit` in the pinned image | 0 vulnerabilities (0 with `--omit=dev`) |
| Dependency scan, chaincode | `npm audit` in the pinned image | 0 vulnerabilities |
| Line endings | `tr -cd '\r'` on the seven new files | 0 carriage returns; `git ls-files --eol` reports `i/lf w/lf` for the tracked shell scripts |
| Fabric suite | not run at baseline | PROGRESS.md records 12 passed in 3007,74 s for the l07 tree. It takes about 50 minutes and a sleeping PC cut an earlier run, so it is not repeated here; see "Could not verify" in `AUDIT_REPORT.md`. |

Facts recorded for the audit:

- `uv run mypy` fails on this host (`mypy.exe` of another interpreter is found first): `py -3 -m mypy` is the command that works, as in the earlier rounds.
- `provenance.test.ts` lists the same 48 `describe` / `test` declarations before and after the l07 edit (the stand-in ledger moved to `test/memory-ledger.ts`), checked with a sorted diff of the declaration lines.
- Experiment for AUD-091: in a copy of `ledger-gateway`, `registerModel` was changed to `evaluateTransaction`, `history` to the transaction name `GetCaseHistoryX` and `getModel` to swapped arguments. `npm test` still reported **105 passed**.
