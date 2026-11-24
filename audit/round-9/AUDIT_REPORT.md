# Audit report, round 9 — SAAMSTIAHF

Date: 2026-11-16 · Scope: the owner's uncommitted `l10-board-bringup` (T1.9) working tree, on top of the committed and pushed `l09-no-phi-guard` @ `9abd20a` (which round 8 audited and fixed). Earlier rounds: `audit/`, `audit/round-2/` to `audit/round-8/`. Tree audited: 4 modified tracked files, 9 new source files, and the 124 generated files of `hw/SAAM/` (`INVENTORY.md`).

## 1. Summary

l10 is the Zybo Z7-10 bring-up spike: a block design with the PS7 and one AXI4-Lite register (`hw/vivado/build.tcl`, `hw/rtl/axil_reg_bringup.vhd`), a console application for the PS (`hw/ps_app/bringup/hello.c`, built by `build_app.py`), the PC side (`hw/host/tests/bringup_support.py`, board tests with the `board` marker) and `--board` in `scripts/test-l.sh`. `PROGRESS.md` is honest about it: the definition of done of T1.9 (boot from the SD card, register written and read from the PS, UART rate measured) is **not met**, because there is no board, no serial port and no Digilent board files here. This audit did not change that.

What it checked, and what it found:

- **The register is correct.** I wrote an AXI4-Lite protocol bench and ran it in the Vivado simulator (`audit/round-9/tools/xsim/`): the register passes, and 12 of 12 mutations of it fail the bench.
- **The documented board command did not work** (AUD-112): `SAAM_ZYBO_PORT=COM5 scripts/test-l.sh --board` runs the local suite first with the port in its environment, and a test of that suite calls `--board` itself. On the board workstation the test would open the serial port in the middle of the local phase and, today, it fails its own assertion, so the board phase is never reached.
- **`hello.c` changes the UART speed too early** (AUD-118): read against the real driver, the wait before `XUartPs_SetBaudRate` looks at the FIFO only, and `XUartPs_SetBaudRate` resets the transmitter at once. The last character of the `B 921600` acknowledgement can be cut. Fixed by the driver's own contract; to be confirmed on the board.
- **The console logic was tested only by word search** (AUD-117): 10 of 12 behavioural mutations of `hello.c` passed every test. A host build of `hello.c` against stub headers, driven by the real `Console` class, now pins them: 52 tests, all 13 mutations killed, and no defect in the parsing.
- Smaller things: a Vivado project of 124 generated files not ignored by git (AUD-114), a mypy error (AUD-115), a board run reported as board access when every test was skipped (AUD-113), two wrong sentences (AUD-116).

| Severity | Count | IDs |
|---|---|---|
| Critical / High | 0 | |
| Medium | 2 | AUD-112, AUD-118 |
| Low | 5 | AUD-113, AUD-114, AUD-115, AUD-116, AUD-117 |
| Info | 0 new, 7 carried over | AUD-109 (round 8); AUD-104, AUD-105, AUD-095 to AUD-098 (rounds 6 and 7), unchanged |

Decisions needed from the user: none for this round. AUD-109 still waits for the spec owner. The T1.9 definition of done waits for the board.

## 2. Coverage

The l09 commits were audited in round 8 and did not change; they are `[=]` in `INVENTORY.md`. The 13 source files of the l10 tree were read in full: the VHDL line by line against the AXI4-Lite handshake rules; `build.tcl` against the commands that its mock test allows; `hello.c` against the driver headers and sources of Vitis 2025.2; the three Python test files and `bringup_support.py` against the console they test; the diff of `scripts/test-l.sh`, `.gitignore`, `test_test_l.py` and `PROGRESS.md`. The 124 generated files of `hw/SAAM/` were counted and sampled (`.sh`, `.xml`, `.wdf`), not read: 30 of them contain the name of the workstation. After the fixes every changed file was read again (§6). Files that round 9 added: `hw/host/tests/test_hello_console.py`, `hw/host/tests/hello_stub/` and the tests of the fixes.

## 3. Baseline

See `BASELINE.md`: local suite exit 0 (Python 431 passed / 3 skipped, `hw/host/tests` 31 passed / 11 deselected, Jest 183 and 212), ruff and format clean, `mypy tests hw/host` with one error, the compile tests of `hello.c` pass (25 passed) against the real Vitis drivers when `XILINX_VITIS` is set. Four probes were run before any change; each one produced a finding or a table row.

## 4. Findings

### AUD-112 — Medium — Test/Correctness — the documented board command fails, and a test of the local suite would open the board
- **Location:** `scripts/test-l.sh:146-157` (`run_local` runs pytest with the caller's environment), `tests/scripts/test_test_l.py:188-195` (`test_board_flag_runs_no_board_tests_and_does_not_open_a_device` calls `scripts/test-l.sh --board`), `hw/BRINGUP.md:54` (the command)
- **Description:** `SAAM_ZYBO_PORT=COM5 scripts/test-l.sh --board` runs the local suite, then the board tests. The local suite includes a test that calls `scripts/test-l.sh --board` (nested, local phase skipped through `SAAM_TEST_L_RUNNING`). That call inherits `SAAM_ZYBO_PORT`, so it runs the board phase for real.
- **Evidence:** on this workstation (no `pyserial`), `SAAM_ZYBO_PORT=COM99 bash scripts/test-l.sh --board` → `1 failed, 430 passed, 3 skipped`, exit 1: the nested output was `11 skipped, 489 deselected in 0.61s` and `board-access: tests-only`, and the assertion `"The board was not opened." in combined` failed. With `pyserial` and a board, the same nested call opens the serial port and runs the 11 board tests (and writes `hw/reports/bringup-uart.json`) inside the local phase, under a test named `…does_not_open_a_device`.
- **Root cause:** the local suite is meant to need no board, but it receives the variable that names the board. The only test that guarded this ran with the variable unset.
- **Impact:** the command that the DoD of T1.9 names cannot succeed. On the workstation that has the board it either aborts before the board phase (`set -e`) or touches the board from the wrong place.
- **Recommended fix:** the local phase never sees `SAAM_ZYBO_PORT`.
- **Status:** Fixed. `run_pytest_local` (a subshell that unsets the variable) runs both pytest calls of `run_local`; the board phase keeps the port. Three tests: the function itself, `run_local` end to end with a probe in place of pytest (both calls print `seen=[unset]`), and the pre-existing test, unchanged. Mutations J1 to J3 (no `unset`, either call back on `run_pytest`) each fail one of them. After the fix `SAAM_ZYBO_PORT=COM99 bash scripts/test-l.sh --board` runs the local suite to the end (454 passed) and reaches the board phase.

### AUD-113 — Low — Test/Docs — `--board` says `board-access: tests-only` when every board test was skipped, and hides why
- **Location:** `scripts/test-l.sh:174-198` (`run_board`)
- **Description:** with the port set, `run_board` printed `board-access: tests-only` whenever pytest exited 0. A run in which every board test is skipped also exits 0, for example when `pyserial` is missing (the fixture skips). The skip reasons were not shown (`-q` without `-rs`).
- **Evidence:** the nested output above: `11 skipped … board-access: tests-only`. `PROGRESS.md` and the script's own help say that a skip is not a pass.
- **Root cause:** the script reports from pytest's exit status, which does not tell a pass from a skip; the port-unset case had its own message, the port-set-but-skipped case did not.
- **Impact:** someone who runs the board command on a machine without `pyserial` reads "tests-only" and may believe the board was exercised.
- **Recommended fix:** show the reasons (`-rs`), and when the port is set and no test passed, say so and fail.
- **Status:** Fixed. The board phase runs `pytest -q -rs`, keeps the output, and without a passed test prints `SAAM_ZYBO_PORT is set but no board test passed: they were skipped (reasons above), so the board was not used.` and `board-access: no`, exit 4. With a passed test it is unchanged. Tests: skipped-only gives exit 4; one passed gives `tests-only` and exit 0; the no-port test now also needs pytest's own reason. Mutations J4 to J6 fail them. Live: `board-port-set.log` (reasons printed, exit 4).

### AUD-114 — Low — Config/Privacy — the Vivado project made by hand sits in `hw/SAAM/` and git does not ignore it
- **Location:** `.gitignore` (only `hw/build/` was added by l10), `hw/SAAM/` (124 untracked files, 1.8 MB)
- **Description:** `build.tcl` opens a project that the user creates by hand. The owner's is `hw/SAAM/SAAM.xpr`, with its caches, run logs, reports and a shell script (`SAAM.runs/impl_1/ISEWrap.sh`).
- **Evidence:** `git status --short -uall` listed 124 files; 30 of them contain the name of the workstation. `PROGRESS.md` already says "do not commit it".
- **Root cause:** nothing but a sentence in `PROGRESS.md` stops `git add -A` or `git add hw`. Committing the folder would also break `test_shell_scripts_are_executable_in_the_git_index` (the `.sh` files would need mode 100755) and publish machine paths.
- **Impact:** low, but it is one careless command from a noisy commit with personal data, and the project name is not fixed (the owner's note waits for it).
- **Recommended fix:** ignore a hand-made Vivado project whatever its name and folder: the project file and the six generated folders, under `hw/`.
- **Status:** Fixed. `.gitignore` gets `hw/**/*.xpr`, `*.cache/`, `*.runs/`, `*.hw/`, `*.ip_user_files/`, `*.sim/`, `*.gen/`, `*.srcs/`. `git status` now lists 0 files of `hw/SAAM/`. 19 tests with `git check-ignore`: ten paths of a Vivado project are ignored, nine paths of the hardware part (`hw/rtl/…`, `hw/vivado/build.tcl`, `hw/sim/Makefile`, `hw/reports/…`) stay versioned. Mutations G1 to G9 (each pattern removed, and `*.sim/` widened to `sim/`) all fail.

### AUD-115 — Low — Test — `mypy` fails on `test_bringup_config.py`
- **Location:** `tests/scripts/test_bringup_config.py:67-81` (`Recorder`)
- **Description:** `Recorder.interp` is typed `object`; eight lines carry `# type: ignore[attr-defined]` (five in `Recorder`, three at the calls of `tcl.interp.eval(`). In `calls()` the ignore is on the line of the closing bracket, and mypy reports the error on the line above (`"object" has no attribute "splitlist"`).
- **Evidence:** `py -3 -m mypy tests hw/host` → 1 error, where rounds 7 and 8 were clean.
- **Root cause:** the interpreter is a `tkinter.Tk` (what `tkinter.Tcl()` returns), typed as `object` to avoid importing `tkinter` at module level; the ignores then hid the type instead of stating it.
- **Impact:** the type check of the tests is red; the ignores hide real mistakes in the mock.
- **Recommended fix:** type the interpreter (`Tk`, imported under `TYPE_CHECKING`) and remove the ignores.
- **Status:** Fixed. `Recorder.__init__(self, interp: Tk)`, the eight ignores removed; `mypy tests hw/host`: no issues in 35 files.

### AUD-116 — Low — Docs — two sentences are wrong
- **Location:** `hw/host/tests/test_bringup.py:4` ("BOOT.bin from hw/ps_app/bringup/build_app.tcl"), `hw/vivado/build.tcl:14-15` ("Nothing outside them is written")
- **Description:** the build script of the application is `build_app.py`. And `build.tcl` writes the block design and the runs into the user's Vivado project, which is outside the two directories that the sentence names.
- **Status:** Fixed (one word; one sentence that now says "Apart from the Vivado project itself").

### AUD-117 — Low — Test — the console of `hello.c` is tested by word search and by compilation only
- **Location:** `tests/scripts/test_bringup_config.py:617-631` (`test_the_ps_app_answers_the_commands_the_host_test_sends`), the compile tests (skipped without Vitis), `hw/host/tests/test_bringup_support.py` (a Python double of the console)
- **Description:** no test runs the logic of `hello.c`: the parsing of the hex and decimal arguments, the limits (8 hex digits, 7 decimal digits, 65 536 echo bytes, 31 characters per line), the baud whitelist, the reply formats. The host side is tested against a Python double *written from* `hello.c`, so a difference between them is invisible.
- **Evidence:** `audit/round-9/tools/mutate_hello.py`, 12 mutations that still compile (`mutations-hello.log`): `BAUD_HIGH` 921600 → 9216000, any baud accepted, 9 hex digits accepted, echo limit doubled, no empty line before `DONE`, write to the next register, upper-case hex, CR no longer ignored, no wait before the baud change, another banner: **10 survive**. Only the base address (a word search) and an unused variable (`-Werror`) are caught.
- **Root cause:** `hello.c` talks to hardware, so it was thought untestable off the board; but only five driver calls touch hardware, and they can be stood in for.
- **Impact:** the board run is the first test of any of this, on the one machine that has the board. A wrong limit or reply costs a day there. The application is a throw-away spike (T4.12 replaces it), which is why this is Low.
- **Recommended fix:** compile `hello.c` unchanged on the host against stub headers, with the UART on pipes and the hardware calls logged, and run the real `Console` class against it.
- **Status:** Fixed. `hw/host/tests/hello_stub/` (four headers and `uart_stub.c`) and `hw/host/tests/test_hello_console.py`: 52 tests (start-up, `H`, `W`/`R` with address check, refused writes and nothing written, unknown commands, the 31/32-character boundary, baud acknowledgement and refusals, echo of every byte value, limits 65 536/65 537, and the host `Console` against the real one: hello, six register patterns, a refused write, both baud rates, a 16 KiB echo). They need `gcc` or `cc` and are skipped with the reason without one. The first run found nothing wrong in `hello.c`'s parsing. Mutations: 13 of 13 killed (`mutations-hello-final.log`). Stated limit: it proves the console logic and the agreement of the two sides, not the UART, the PL or the board.

### AUD-118 — Medium — Correctness — `hello.c` changes the baud rate before the last character has left
- **Location:** `hw/ps_app/bringup/hello.c:174-177` (`command_baud`)
- **Description:** the console answers `B 921600` at the old rate, waits with `while (!XUartPs_IsTransmitEmpty(&uart))`, then calls `XUartPs_SetBaudRate`. In the driver, `XUartPs_IsTransmitEmpty` tests the **FIFO** empty bit only; the character being shifted out is no longer in the FIFO. `XUartPs_SetBaudRate` then disables the UART, writes the new divisors and resets the transmitter at once.
- **Evidence:** driver `uartps_v3_17` of Vitis 2025.2: `xuartps.h:450` (`XUartPs_IsTransmitEmpty` → `XUARTPS_SR_TXEMPTY`), `xuartps_hw.h:432-441` (`XUartPs_IsTransmitActive` → `XUARTPS_SR_TACTIVE`, "TX state machine active", the macro made for this), `xuartps.c:520-610` (`XUartPs_DisableUart`, then `XUARTPS_CR_TXRST | XUARTPS_CR_RXRST`). A character takes 87 µs at 115 200 baud; the divisor search of `XUartPs_SetBaudRate` is shorter.
- **Root cause:** the wait looks at the FIFO, not at the transmitter.
- **Impact:** the last byte (the LF) of the acknowledgement can be cut. The host reads until `\r\n`, so `Console.set_baud` times out ("no answer from the board") and the 921 600-baud measurement of the DoD fails, or fails at random.
- **Recommended fix:** wait until the FIFO is empty **and** the transmit state machine is idle.
- **Status:** Fixed in the code: `while (!XUartPs_IsTransmitEmpty(&uart) || XUartPs_IsTransmitActive(uart_base))`. It compiles with `-Wall -Wextra -Werror` against the real drivers in both APIs. The host test now checks the order (the stub's transmitter is still active for two calls; the baud change must come after `TXACTIVE 0`), and mutation H13 (the new condition dropped, which is the old code) fails it. **Not verified on the board**: only the driver's documented behaviour and the order of calls are checked here.

## 5. Fix plan and order followed

AUD-112 first (the DoD command), then AUD-118 (the only defect that can fail a measurement), AUD-113, AUD-117 (its harness is what found AUD-118's test), AUD-114, AUD-115, AUD-116.

## 6. Verification

Run on the final tree, after the fixes (`final-test-l.log`, `board-port-set.log`, `xsim-register.log`, `mutations-*.log`).

| Check | Baseline | After the fixes |
|---|---|---|
| `bash scripts/test-l.sh` | exit 0; Python 431 passed, 3 skipped; `hw/host/tests` 31 passed; Jest 183 and 212 | exit 0; Python **454 passed**, 3 skipped (+23: 4 in `test_test_l.py`, 19 in `test_bringup_config.py`); `hw/host/tests` **83 passed** (+52); Jest 183 and 212 |
| `SAAM_ZYBO_PORT=COM99 bash scripts/test-l.sh --board` | exit 1 in the local phase | local phase green (454 passed); board phase: 11 skips with their reasons, `no board test passed`, `board-access: no`, exit 4 (no `pyserial`) |
| `ruff check .`, `ruff format --check .`, `mypy tests hw/host` | pass, pass (101 files), **1 error** | pass, pass (109 files), pass (35 files) |
| `bash -n` on every `.sh` | pass | pass |
| `git diff --check` | not run | exit 0 (CRLF notices only) |
| Untracked, not ignored files of `hw/SAAM/` | 124 | 0 |
| `test_bringup_config.py` with the real Vitis drivers (`XILINX_VITIS`) | 25 passed | 44 passed (the two compile tests of the fixed `hello.c` included) |
| Mutations of `hello.c` (13, all compile) | 10 of 12 survive | **13 of 13 killed** (`mutations-hello-final.log`) |
| Mutations of the fixes (15: J1 to J6, G1 to G9) | n/a | 15 of 15 killed (`mutations-fixes.log`) |
| `axil_reg_bringup.vhd` in the Vivado simulator | not run | protocol bench PASS; 12 of 12 mutations of the register killed (`xsim-register.log`) |
| Real Linux (WSL2 Ubuntu 22.04): `hw/host/tests`, `test_bringup_config.py`, `test_test_l.py` (without the one nested full run) | n/a | 130 passed, 14 skipped (12 need `tkinter`, which that Python lacks; 2 need Vitis); includes the host build of `hello.c` with `gcc` and the `git check-ignore` tests |

**Re-audit.** Every file the audit changed or added was read again: `scripts/test-l.sh`, `test_test_l.py`, `test_bringup_config.py`, `.gitignore`, `hello.c`, `hello_stub/*`, `test_hello_console.py`, `test_bringup.py`, `build.tcl` (header), `hw/BRINGUP.md`, `PROGRESS.md`. Two mistakes of the audit's own first versions were caught by its tests and fixed in the same round: the fixture of the host-console tests read the start-up bytes with one `read(n)` on an unbuffered pipe, which returns what has arrived (it now loops), and a newline in a C string literal of the stub came out of an editing script and failed to compile. No new finding came out of the re-read.

**Not verified.**
- The board itself: boot from the SD card, the register from the PS, the UART rate, and therefore AUD-118 on hardware. The T1.9 definition of done stays open (as `PROGRESS.md` says).
- The full Vivado flow of `build.tcl` with the Digilent board files and `build_app.py` (the owner could not run them either; `vitis.create_client()` fails on a UTF-8 decoding error on a French-locale workstation). Only their mock tests and the compile of `hello.c` against the real drivers were run.
- `hello.c` as an ARM binary (no emulator was run); the host build proves the logic, not the compiled ARM code.
- `test_bringup.py` itself: its `console` fixture runs only with `pyserial` and a port.
- A native Linux host (WSL2 only), the Fabric tests (nothing in l10 touches Fabric), `npm audit` (no JavaScript changed).

## 7. Unresolved

| ID | Severity | Status | Why | Risk of leaving it | What is needed |
|---|---|---|---|---|---|
| AUD-109 | Info | Deferred (round 8) | a stricter NFR-03 guard needs a version shape in the on-chain schema | an unspaced name or an odd date in `softwareVersion` is not caught | decision of the spec owner |
| AUD-104, AUD-105 | Info | Open (round 7) | copied probe helpers; contract tests in four files | none today | the owner's decision |
| AUD-095 to AUD-098 | Info | Open (round 6) | decisions of the spec owner or of B | see round 6 | unchanged |

Observed, no defect:
- `hw/vivado/build.tcl` needs a project (`SAAM_VIVADO_PROJECT` or `-tclargs`), so the command in the `AGENTS.md` table (`vivado -mode batch -source hw/vivado/build.tcl`) fails with "no project". `hw/BRINGUP.md` has the right command. `AGENTS.md` is the team's file.
- `hello.c` ignores the return value of `XUartPs_SetBaudRate`: the acknowledgement is sent before the change, so a refusal cannot be reported. A refused 921 600 would show as a timeout on the host. The driver returns an error above 3 % divisor error; the input clock of the board decides it.
- Hygiene of the new files: they are plain LF files, and l10 adds no `.sh` file (the one of `hw/SAAM/` is now ignored), so nothing needs `git add --chmod=+x` this time except `audit/round-9/tools/…` if a script is added there (none is).
