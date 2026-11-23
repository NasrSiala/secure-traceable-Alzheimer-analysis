# Baseline — round 11

Date: 2026-11-19. Branch: `l11-sha256-compress-core` at `f2841e5`, plus the uncommitted l12 padder. No install step: the working tree already has pytest and ruff.

| Check | Command | Result |
|---|---|---|
| SHA tests | `py -3 -m pytest -q -o addopts= tests/scripts/test_sha256_core.py tests/scripts/test_sha256_padder.py` | 40 passed, 2 skipped (both skips: no `xvhdl` on PATH) |
| Ruff | `py -3 -m ruff check` and `ruff format --check` on `hw/sim/sha_support.py`, `test_sha256.py`, `test_sha256_padder.py`, `tests/scripts/test_sha256_core.py`, `test_sha256_padder.py` | All checks passed; 5 files already formatted |
| GHDL / cocotb / xsim | `import cocotb`; `Get-Command ghdl, cocotb-config, xvhdl` | `ModuleNotFoundError: No module named 'cocotb'`. `ghdl`, `cocotb-config` and `xvhdl` are not commands. |
| Full `scripts/test-l.sh`, npm audit, app start, Fabric | not run | No Fabric, gateway or chaincode file is in this diff. Recorded under Could not verify. |

The xsim pass of `sha256_padder_tb` (PROGRESS.md, 2026-11-19, `SHA256_PADDER_TB PASSED`) was not repeated: this machine has no `xvhdl`.
