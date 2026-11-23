# Codebase Audit Report — SAAMSTIAHF, round 10

Date: 2026-11-19 · Branch: `l10-board-bringup` @ `27d7dd9` · Auditor: codebase-audit skill

## 1. Executive summary

This round covers the uncommitted SHA-256 compression core (`l11`), not a second full pass over the committed tree. Rounds 1–9 already inspected that tree. Two defects were in the new files: the entity comment tells the next block to sample `done` one cycle early, and the cocotb makefile builds `PYTHONPATH` with a colon, which Windows Python ignores.

| Severity | Found | Fixed | Workaround | Deferred | Won't fix | Could not verify |
|---|---|---|---|---|---|---|
| Critical | 0 | 0 | 0 | 0 | 0 | 0 |
| High | 0 | 0 | 0 | 0 | 0 | 0 |
| Medium | 0 | 0 | 0 | 0 | 0 | 0 |
| Low | 2 | 2 | 0 | 0 | 0 | 0 |
| Info | 1 | 0 | 0 | 0 | 1 | 0 |

Top risks:
1. AUD-119 — a padder written from the old comment would read `digest` one cycle before `H` is updated.
2. The cocotb bench and GHDL were still not executed (pre-existing, PROGRESS 2026-11-17).

## 2. Scope and coverage

- Stack: Python tests, VHDL-2008 SHA-256 core, cocotb makefile, Vivado xsim testbench.
- Files read this round: 9. The other tracked files are unchanged since `27d7dd9` and were inspected in earlier rounds. See `INVENTORY.md`.
- A first attempt to re-read the chaincode, gateway, and Fabric tree with parallel reviewers was interrupted and produced no findings.

## 3. Baseline

See `BASELINE.md`. After the fixes: `tests/scripts/test_sha256_core.py` — 35 passed, 1 skipped.

## 4. Findings

### AUD-119 — the core comment samples `done` one cycle early

- **Severity:** Low
- **Category:** Docs
- **Location:** `hw/rtl/sha256_core.vhd:18-21` (before the fix)
- **Description:** The comment said `done` is visible 65 cycles after the edge that takes the 16th word. The testbench that PROGRESS records as passing asserts `busy` for 65 cycles and `cycle - accepted_at = 66`.
- **Evidence:** `sha256_core_tb.vhd:163` and `:168`; PROGRESS.md row for T3.18, “done 66 fronts après le dernier mot”.
- **Root cause:** The accepting edge is not one of the 65 busy cycles. `done` rises on the following edge, when the add state is left.
- **Impact:** l12, if written from the comment, would read `digest` while the core is still in the add state, before `H` is updated.
- **Recommended fix:** State both numbers the way the testbench measures them.
- **Status:** Fixed
- **Fix applied:** comment in `hw/rtl/sha256_core.vhd`. The RTL and the testbench assertions were not changed.

### AUD-120 — cocotb's `PYTHONPATH` uses a colon on Windows

- **Severity:** Low
- **Category:** Config
- **Location:** `hw/sim/cocotb.mk:21` (before the fix)
- **Description:** `export PYTHONPATH := $(SIM_DIR):$(PYTHONPATH)` uses `:`. The Windows interpreter splits that variable on `;`, so `import sha_support` fails when `make -C hw/sim cocotb` is run with the Windows `python`.
- **Evidence:** the makefile line; `test_sha256.py` imports `sha_support` as a top-level module.
- **Root cause:** The separator was written for a POSIX shell only. This host is Windows, which is also where the xsim run was done.
- **Impact:** The bench cannot start on this host even after GHDL and cocotb are installed, until the path is fixed. It has never been run (GHDL and cocotb are absent).
- **Recommended fix:** Pick `;` when `OS` is `Windows_NT`.
- **Status:** Fixed
- **Fix applied:** `hw/sim/cocotb.mk`; `tests/scripts/test_sha256_core.py` asserts `Windows_NT` and `PYSEP := ;`. 35 passed, 1 skipped.

### AUD-121 — hashlib stands in for `saam/hashing`

- **Severity:** Info
- **Category:** Architecture
- **Location:** `hw/sim/test_sha256.py:18`, `hw/sim/sha_support.py:4-5`
- **Description:** AGENTS.md says cocotb benches use `saam/hashing`. That package is not in the tree. The bench uses `hashlib`, and PROGRESS already records the substitution.
- **Status:** Won't fix. Replacing it before `saam/hashing` exists would invent a second oracle. The VHDL literals are checked against `hashlib` by `test_sha256_core.py`.

## 5. Fix plan

Both low findings are fixed. No decision is waiting on the user.

## 6. Verification

| Check | Before | After |
|---|---|---|
| `test_sha256_core.py` | 35 passed, 1 skipped | 35 passed, 1 skipped |
| ruff / format on the bench Python | pass | pass |
| xsim | not run (no `xvhdl`) | not run |
| cocotb | not run (tools absent) | not run; the path bug is fixed but unexecuted |
| Fabric suite | not run | not run |

Regressions: none observed in the checks that ran.

## 7. Unresolved

- GHDL, cocotb, and a fresh xsim run were not executed here. The last xsim pass is the one recorded on 2026-11-17.
- The committed tree was not re-read line by line after the interrupted review.
- T1.9 still has no board result (round 9). That is unchanged.
