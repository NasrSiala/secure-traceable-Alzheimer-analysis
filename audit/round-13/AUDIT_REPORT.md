# Codebase Audit Report — SAAMSTIAHF

Date: 2026-11-20 · Branch: `l12-sha256-padder-multiblock` @ `b2e2b3b`, plus uncommitted hardware and the round-12 fixes · Auditor: codebase-audit skill

## 1. Executive summary

The new uncommitted hardware is the FIR decimator, the two AXI wrappers, and the IF-14 command file. One defect is in that command file: each SHA-256 digest word was stored little-endian, so the first byte of the hash would have been the last byte of the register. That is fixed and the host program prints `SAAM_CMD_HOSTCHECK PASSED`. `saam_dispatch` still answers only INFO.

| Severity | Found | Fixed | Deferred | Won't fix |
|---|---|---|---|---|
| Critical | 0 | 0 | 0 | 0 |
| High | 0 | 0 | 0 | 0 |
| Medium | 2 | 1 | 1 | 0 |
| Info | 2 | 0 | 0 | 2 |

## 2. Coverage

Read in full this round: `hw/rtl/fir_decim.vhd`, `hw/rtl/sha256_axi.vhd`, `hw/rtl/fir_axi.vhd`, `saam/dsp/fir_fixed.py`, `hw/host/uart_framing.py`, `hw/ps_app/saam_cmd.c`, `hw/ps_app/saam_cmd_hostcheck.c`, `hw/host/tests/test_uart.py`. Read in part: `hw/rtl/fir_coeffs_pkg.vhd` (header and taps), `hw/host/zybo_client.py`, `hw/sim/Makefile` targets. Specs, Fabric, and the chaincode were not re-read. Lockfiles and generated vector files were not read line by line.

## 3. Baseline

`py -3 -m pytest -q -o addopts= hw/host/tests/test_uart.py tests/scripts/test_fir_decim.py`: 12 passed, 1 skipped. The host C check was compiled with `gcc -Wall -Wextra -Werror` and printed `SAAM_CMD_HOSTCHECK PASSED`. Fabric was not started.

## 4. Findings

### AUD-132 — digest words were written little-endian

- **Severity:** Medium
- **Category:** Correctness
- **Location:** `hw/ps_app/saam_cmd.c` (`saam_sha256`)
- **Description:** `DIGEST0` holds the first four hash bytes, with the first byte in bits 31..24. `wr_le` reversed each word.
- **Evidence:** `sha256_axi.vhd` maps `digest(255 downto 224)` to address `0x10`. `abc` begins `ba 78 16 bf`. Little-endian store yields `bf 16 78 ba`.
- **Root cause:** Frame fields are little-endian. The digest registers are not.
- **Impact:** A later IF-14 SHA-256 reply would not match `hashlib`. INFO and the CRC stay little-endian and were already checked.
- **Recommended fix:** Write digest words big-endian.
- **Status:** Fixed
- **Fix applied:** `wr_be` for the eight digest words. `saam_cmd_hostcheck` expects `BA 78 16 BF` then `8F … EA`. `gcc -Wall -Wextra -Werror` and the program printed `SAAM_CMD_HOSTCHECK PASSED`.

### AUD-133 — the command loop does not run SHA-256 or FIR

- **Severity:** Medium
- **Category:** Completeness
- **Location:** `hw/ps_app/saam_cmd.c` (`saam_dispatch`)
- **Description:** The file header names commands `0x10` and `0x20`. `saam_dispatch` returns -2 for both. Only INFO is framed.
- **Evidence:** The `else` branch after `CMD_INFO` is `return -2`. `saam_sha256` and `saam_fir_push` are separate. The response scratch buffer is 64 bytes.
- **Root cause:** INFO fits in that buffer. A FIR reply is one status byte plus the int16 outputs and does not.
- **Impact:** The Python `PsModel` used by `test_uart.py` does answer SHA-256 and FIR. The C loop on the PS would not.
- **Recommended fix:** Frame those commands into the caller’s response buffer, and poll the AXI status the way `saam_sha256` already does. Not done here: the host MMIO stub does not model the padder or the FIR, so a wired dispatch cannot be proved with this stub.
- **Status:** Deferred

### AUD-134 — coefficient id uses hashlib

- **Severity:** Info
- **Category:** Architecture
- **Location:** `saam/dsp/fir_fixed.py` (`coef_id`)
- **Description:** The id is `hashlib.sha256` of `fir_coeffs.json`. The project rule is that every fingerprint goes through `saam/hashing`.
- **Evidence:** `hashlib.sha256(_JSON_PATH.read_bytes()).hexdigest()[:8]`. There is no `saam/hashing` package.
- **Root cause:** Same gap as AUD-121. The benches and this id use hashlib until that package exists.
- **Impact:** None while the package is absent. The id matches the constant in `fir_coeffs_pkg.vhd` (`ca0e824c`) via the UART test.
- **Recommended fix:** Switch the call when `saam/hashing` exists.
- **Status:** Won't fix

### AUD-135 — Xilinx interface attributes on the AXI wrappers

- **Severity:** Info
- **Category:** Architecture
- **Location:** `hw/rtl/sha256_axi.vhd`, `hw/rtl/fir_axi.vhd`
- **Description:** Both entities carry `X_INTERFACE_INFO` attributes.
- **Evidence:** The attributes name the clock, the active-low reset, and `s_axi`.
- **Root cause:** They tell Vivado how to pack the slave. They are not a `unisim` or `xpm` primitive.
- **Impact:** None on the arithmetic. The RTL still uses only `numeric_std`.
- **Recommended fix:** Leave them. Removing them makes the block-design hookup manual.
- **Status:** Won't fix

## 5. Fix plan

AUD-132 is done. AUD-133 waits for an MMIO model that can finish a hash and a FIR run. AUD-134 and AUD-135 stay.

## 6. Verification

| Check | Result |
|---|---|
| `test_uart.py` and `test_fir_decim.py` | 12 passed, 1 skipped |
| `saam_cmd_hostcheck` | `SAAM_CMD_HOSTCHECK PASSED` |
| Fabric / xsim | not run |

## 7. Unresolved

| ID | Status | To resolve |
|---|---|---|
| AUD-133 | Deferred | Wire SHA-256 and FIR in `saam_dispatch` once the host stub can complete those AXI sequences |
| AUD-134 | Won't fix | `saam/hashing` does not exist yet |
| AUD-135 | Won't fix | Attributes are the Vivado bus hookup |

## 8. Re-audit

Re-read `saam_sha256` after the edit. INFO and the CRC still use `wr_le`. Only the digest words use `wr_be`. No new finding.
