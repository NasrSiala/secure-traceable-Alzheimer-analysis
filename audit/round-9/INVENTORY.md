# Audit inventory, round 9 — SAAMSTIAHF

Date: 2026-11-16 · Branch: `l09-no-phi-guard` @ `9abd20a` (pushed) + the owner's uncommitted `l10-board-bringup` (T1.9) working tree · Source of list: `git status --short -uall`, `git diff HEAD`.

Rounds 1 to 8 read every file that existed up to `9abd20a` (round 8 read the l09 tree in full and again after its fixes). Since then 4 tracked files changed and 9 source files were added by l10; the audit itself then changed or added more. Round 9 read all of them and, after the fixes, read the changed ones again (`AUDIT_REPORT.md` §6).

Legend: `[x]` read in full, and read again after the fixes when the audit changed it · `[d]` read as a diff against `HEAD` · `[=]` unchanged since the last round · `[-]` excluded.

## Hardware part (`hw/`)

- [x] `rtl/axil_reg_bringup.vhd` (new; **not changed**: simulated, `audit/round-9/tools/xsim/`)
- [x] `vivado/build.tcl` (new; **changed: header sentence, AUD-116**)
- [x] `ps_app/bringup/hello.c` (new; **changed: AUD-118**)
- [x] `ps_app/bringup/build_app.py` (new)
- [x] `BRINGUP.md` (new; **changed: a paragraph on the host tests**)
- [x] `host/tests/bringup_support.py`, `test_bringup.py` (**changed: one word, AUD-116**), `test_bringup_support.py` (new)
- [x] `host/tests/test_hello_console.py`, `host/tests/hello_stub/*` (**new, audit: AUD-117, AUD-118**)
- [-] `SAAM/` (124 generated files of the user's Vivado project: caches, run logs, `webtalk` files, `ISEWrap.sh`; not read line by line, **now ignored by git: AUD-114**)

## Scripts and tests

- [d] `scripts/test-l.sh` (the `--board` message; **changed: AUD-112, AUD-113**)
- [d] `tests/scripts/test_test_l.py` (one test added by l10; **changed: 4 tests added, 1 strengthened**)
- [x] `tests/scripts/test_bringup_config.py` (new, 631 lines; **changed: AUD-114 tests, AUD-115**)
- [x] `tests/conftest.py`, `tests/scripts/gateway_run_support.py` (read to check how the new tests run the scripts)

## Configuration and documents

- [d] `.gitignore` (`hw/build/`; **changed: AUD-114**)
- [x] `PROGRESS.md` (T1.9 proof row, decision row, "Problèmes", "Trouvé, non construit"; **changed: the T1.9 row, a "Problèmes" row, the `hw/SAAM/` row**)
- [x] `docs/specs/08-implementation-plan-L.md` §l10, `AGENTS.md`: read as the reference (unchanged)
- [=] everything else (no change since round 8)

## Vendor sources read as the reference

- `uartps_v3_17` of Vitis 2025.2 (`xuartps.c`, `xuartps.h`, `xuartps_hw.h`): `XUartPs_SetBaudRate`, `XUartPs_IsTransmitEmpty`, `XUartPs_IsTransmitActive`.

## Audit files

- `audit/round-9/` (this round): `BASELINE.md`, `AUDIT_REPORT.md`, `INVENTORY.md`, `CHANGES.md`, logs, `tools/` (mutation runners, the simulator bench, the edit scripts)
- [-] `**/node_modules`, `**/dist`, `**/dist-test`, `fabric/wallet`, `fabric/.runtime`, `__pycache__`: generated, ignored by git
