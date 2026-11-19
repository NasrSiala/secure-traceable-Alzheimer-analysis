# Baseline, round 9 — SAAMSTIAHF

Taken on 2026-11-16 before any round-9 change. State: branch `l09-no-phi-guard` @ `9abd20a` (pushed, round 8 included) plus the owner's uncommitted `l10-board-bringup` (T1.9) working tree: 4 modified tracked files (`.gitignore`, `PROGRESS.md`, `scripts/test-l.sh`, `tests/scripts/test_test_l.py`), 9 new source files (`hw/BRINGUP.md`, `hw/rtl/axil_reg_bringup.vhd`, `hw/vivado/build.tcl`, `hw/ps_app/bringup/{hello.c,build_app.py}`, `hw/host/tests/{bringup_support,test_bringup,test_bringup_support}.py`, `tests/scripts/test_bringup_config.py`) and 124 generated files of a Vivado project in `hw/SAAM/` that git did not ignore. Host: Windows 11, Git Bash, Docker Desktop running, no Node on the PATH (the TypeScript checks run in the pinned `node:20.20.2-bookworm` image), Python 3.14 via `py -3`, no `pyserial`, MSYS2 `gcc` 13.2. AMD tools 2025.2 are installed under `E:\AMDDesignTools` but are not on the PATH. A second host was used for the Linux checks: WSL2 Ubuntu 22.04 (Python 3.10, `gcc`, no `tkinter`).

| Check | Command | Result |
|---|---|---|
| Local suite | `bash scripts/test-l.sh` (`baseline-test-l.log`) | exit 0. Python: **431 passed, 3 skipped, 24 deselected** (39.11 s); the 3 skips are the two compile tests of `hello.c` (no Vitis on the PATH) and one NTFS permission test. `hw/host/tests`: **31 passed, 11 deselected** (the 11 `board` tests). Jest `chaincode/provenance` 183, `ledger-gateway` 212. |
| Python lint / format | `py -3 -m ruff check .`, `py -3 -m ruff format --check .` | pass / pass (101 files) |
| Python types | `py -3 -m mypy tests hw/host` | **1 error**: `tests/scripts/test_bringup_config.py:80: "object" has no attribute "splitlist"` (AUD-115) |
| Shell syntax | `bash -n` on every `fabric/*.sh`, `fabric/lib/*.sh`, `scripts/*.sh` | pass |
| Compile of `hello.c` against the real drivers | `XILINX_VITIS=E:/AMDDesignTools/2025.2/Vitis pytest tests/scripts/test_bringup_config.py` | 25 passed (the two compile tests run: ARM GCC 13.3, `-Wall -Wextra -Werror`, device-id API and SDT API). The owner's claim in `PROGRESS.md` holds. |
| Fabric tests | `pytest -m fabric` | 24 collected, not run (nothing in l10 touches Fabric) |
| Dependency scan | `npm audit` | not run: no JavaScript file changed since round 8 |
| Untracked, not ignored | `git status --short -uall` | **124 files of `hw/SAAM/`** (AUD-114) |

Behaviour probed before any change:

| Probe | Result |
|---|---|
| `SAAM_ZYBO_PORT=COM99 bash scripts/test-l.sh --board` (the command of `hw/BRINGUP.md`) | **exit 1, before the board phase**: the local suite fails `test_board_flag_runs_no_board_tests_and_does_not_open_a_device`; the nested call printed `11 skipped, 489 deselected` and `board-access: tests-only` (AUD-112, AUD-113) |
| `audit/round-9/tools/xsim/run_xsim.py` (Vivado simulator, protocol bench written for this round) on `axil_reg_bringup.vhd` | **PASS**, and 12 of 12 mutations of the register are caught: no defect in the register |
| `audit/round-9/tools/mutate_hello.py` (12 mutations of `hello.c` that still compile, tests of the tree) | **10 survive** (baud limits, hex digit limit, echo limit, reply formats, register offset, CR handling, wait before the baud change, banner): the console is tested by word search and by compilation only (AUD-117) |
| Real UART driver, `uartps_v3_17` of Vitis 2025.2: `xuartps.h:450`, `xuartps_hw.h:441`, `xuartps.c:520` | `XUartPs_IsTransmitEmpty` tests the FIFO bit only; the shifter has its own `XUartPs_IsTransmitActive`; `XUartPs_SetBaudRate` disables the UART and resets the transmitter at once (AUD-118) |

Baseline failures: the board command (AUD-112) and the mypy error (AUD-115). Everything listed above as surviving or not handled is a finding.
