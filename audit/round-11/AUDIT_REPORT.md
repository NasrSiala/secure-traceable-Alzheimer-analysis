# Codebase Audit Report — SAAMSTIAHF

Date: 2026-11-19 · Commit/branch audited: `l11-sha256-compress-core` @ `f2841e5`, plus uncommitted l12 · Auditor: codebase-audit skill

This round is `audit/round-11/`. Rounds 1–10 stay where they are. `audit/AUDIT_REPORT.md` is round 1 and was not overwritten.

## 1. Executive summary

The uncommitted work is the SHA-256 padder (`sha256_padder`) in front of the already simulated compression core. The padder RTL matches FIPS 180-4 padding for the cases traced (empty, 3, 4, 55, 56, 60, 63 and 64 bytes) and the host tests check every shared vector against `hashlib`. One real defect is in the cocotb bench of the core, which has never been executed: it kept `word_valid` high across the 65 busy cycles. That bench was corrected. It still has not been run, because GHDL and cocotb are not installed.

| Severity | Found | Fixed | Workaround | Deferred | Won't fix | Could not verify |
|---|---|---|---|---|---|---|
| Critical | 0 | 0 | 0 | 0 | 0 | 0 |
| High | 0 | 0 | 0 | 0 | 0 | 0 |
| Medium | 1 | 1 | 0 | 0 | 0 | 0 |
| Low | 1 | 0 | 0 | 0 | 1 | 0 |
| Info | 1 | 0 | 0 | 0 | 0 | 1 |

Top risks:

1. AUD-122 — the core cocotb bench would mis-feed the 16th word. Source fixed; simulation not run.
2. AUD-124 — GHDL, cocotb and xsim are absent here, so neither hardware bench was executed in this round.

## 2. Scope and coverage

- Stack: VHDL-2008 core and padder, Python benches and pytest, Make. Fabric, the gateway and the chaincode are unchanged in this diff and were not re-read.
- This round read, in full, the padder RTL, its VHDL bench, both cocotb benches, `sha_support.py`, both Makefiles, `sha256_core.vhd`, and `tests/scripts/test_sha256_padder.py`. `tests/scripts/test_sha256_core.py` was read from the Makefile tests through the cocotb structure test, and at the assertion added for AUD-122.
- Files not read this round are `[ ]` in `audit/round-11/INVENTORY.md`. They were inspected in rounds 1–10 and are not claimed as re-read. Lockfiles, logs, the slide deck and the vector file are `[-]`.
- The vector file `hw/sim/vectors/sha256_padder_random.txt` was not read line by line. `test_the_shared_vectors_match_hashlib_and_the_fixed_seed` checked every row against `hashlib`.

## 3. Baseline (before changes)

See `audit/round-11/BASELINE.md`. Before the bench edit: 40 passed, 2 skipped. Ruff was clean. The same pytest result holds after the edit.

## 4. Findings

### AUD-122 — core cocotb bench holds word_valid across the compression

- **Severity:** Medium
- **Category:** Test
- **Location:** `hw/sim/test_sha256.py` (`put_word`, previously the loop that waited on `word_ready` while `word_valid` stayed 1)
- **Description:** Cocotb reads `word_ready` after the clock edge. On the 16th word the core leaves `S_LOAD` and `word_ready` falls on that same edge. The old loop therefore did not retire the word, left `word_valid` at 1 for the 65 busy cycles, and presented that word again as the first word of the next block.
- **Evidence:** `sha256_core.vhd` sets `word_ready` only in `S_LOAD`, and the 16th word moves `state` to `S_ROUNDS` on the accepting edge. The padder bench (`hw/sim/test_sha256_padder.py`, `put_beat`) already applies a beat only when ready is high and drops it after one edge, and its comment says why. The VHDL core bench reads `word_ready` in the same delta as the edge, so it still sees the pre-edge 1. That VHDL bench is the one xsim ran. This cocotb file has never been run (PROGRESS.md, 2026-11-17).
- **Root cause:** The core bench was written for the VHDL delta-cycle read. Cocotb's read is after the update.
- **Impact:** `make -C hw/sim cocotb` would fail, or hash the wrong digest, on the first block. The xsim VHDL bench is unaffected.
- **Recommended fix:** Offer each word for one edge only, after `word_ready` is already 1.
- **Status:** Fixed
- **Fix applied:** `hw/sim/test_sha256.py` and a structure assertion in `tests/scripts/test_sha256_core.py`. Pytest: 40 passed, 2 skipped. The bench itself was not simulated (AUD-124).

### AUD-123 — a last beat with in_bytes above 4 is dropped while in_ready stays 1

- **Severity:** Low
- **Category:** Correctness
- **Location:** `hw/rtl/sha256_padder.vhd:127` and `hw/rtl/sha256_padder.vhd:185`
- **Description:** `in_bytes` is three bits, so 5, 6 and 7 are representable. The last-beat branch accepts only `nbytes <= 4`. `in_ready` does not look at the count, so a ready/valid master records a transfer that the padder ignored. The message then waits in `PH_MSG`.
- **Evidence:** Header lines 15–18 define the legal count as 0 to 4. The accept condition is `if nbytes <= 4` with no else. `in_ready` is `phase = PH_MSG and pending_valid = '0' and init = '0'`.
- **Root cause:** Illegal codes are ignored instead of refusing the handshake. The port is three bits because 0–4 does not fit in two.
- **Impact:** Only a master that drives 5, 6 or 7. Every vector and both benches send 0–4. A legal message is unchanged.
- **Recommended fix:** Leave the contract as 0–4. Do not change the handshake without a simulator run: holding `in_ready` low on an illegal count would stall, and that failure mode is not specified.
- **Status:** Won't fix

### AUD-124 — GHDL, cocotb and xsim were not run

- **Severity:** Info
- **Category:** Test
- **Location:** `hw/sim/test_sha256.py`, `hw/sim/test_sha256_padder.py`, `hw/sim/Makefile`
- **Description:** The cycle-accurate benches cannot be executed on this machine.
- **Evidence:** `import cocotb` raises `ModuleNotFoundError`. `ghdl`, `cocotb-config` and `xvhdl` are not on PATH. Pytest skips both xsim tests for that reason.
- **Root cause:** The tools are not installed. The recorded xsim passes are from 2026-11-17 (core) and 2026-11-19 (padder), on another setup.
- **Impact:** AUD-122 is fixed in source only. A regression in the padder since that xsim run would not show up here.
- **Recommended fix:** On a machine with GHDL and cocotb, run `make -C hw/sim cocotb`. With Vivado, `make -C hw/sim xsim-padder`.
- **Status:** Could not verify

## 5. Fix plan

1. AUD-122 first: the cocotb driver. Done in source.
2. AUD-123: no RTL edit.
3. AUD-124: needs the tools. Not installed in this round.

Needs a user decision: none. Open items from rounds 6–10 (AUD-082, AUD-084, AUD-095 to AUD-098, AUD-104, AUD-105, AUD-109, AUD-121) were not re-opened and not re-tested.

## 6. Verification (after changes)

| Check | Before | After |
|---|---|---|
| SHA pytest | 40 passed, 2 skipped | 40 passed, 2 skipped |
| Ruff on the five Python files | clean | clean |
| Type check | not run (no `pyproject.toml`; these files are outside `saam/`) | not run |
| Build / xsim / cocotb | not run (tools absent) | not run |
| Dependency scan | not run | not run |
| E2E | not applicable to this delta | not run |

Regressions: none in the pytest that ran. The cocotb bench was not executed, so AUD-122 is not proven on a simulator.

## 7. Unresolved

| ID | Status | Reason | Risk of leaving it | To resolve |
|---|---|---|---|---|
| AUD-122 | Fixed in source | Simulator absent | The driver can still be wrong about the 65-cycle count under cocotb's edge order | `make -C hw/sim cocotb` |
| AUD-123 | Won't fix | Out of contract; a stall is unspecified | A master that sends `in_bytes` of 5–7 hangs or hashes the wrong tail | Specify the illegal-count behavior, then simulate it |
| AUD-124 | Could not verify | No GHDL, cocotb or xvhdl | Padder RTL and the new cocotb timing count are unchecked here | Install the tools, or use the Vivado machine |

## 8. Re-audit

Re-read `put_word` and `run_block` after the edit. The new driver drops `word_valid` on the accepting edge and does not sample `word_ready` while valid is high. No new finding. The rest of the tree was not re-read.
