# Baseline — round 10

Date: 2026-11-19. Branch: `l10-board-bringup` @ `27d7dd9`, plus the uncommitted `l11-sha256-compress-core` tree.

The full `./scripts/test-l.sh --fabric` was not started. Rounds 8 and 9 already recorded it, and this round changes no Fabric, chaincode, or gateway file. A first attempt to run the local suite and three read-only review agents was interrupted before any result was saved.

| Check | Command | Result |
|---|---|---|
| SHA-256 unit tests | `py -3 -m pytest -q -o addopts= tests/scripts/test_sha256_core.py` | 35 passed, 1 skipped (Vivado xsim not found on PATH this session) |
| Ruff | `py -3 -m ruff check` and `ruff format --check` on the three Python files of the bench | pass |
| xsim | `make -C hw/sim xsim` | not re-run: no `xvhdl` on PATH. PROGRESS.md records a pass on 2026-11-17 (Vivado 2025.2) |
| cocotb | `make -C hw/sim cocotb` | not run: GHDL and cocotb are not installed (already recorded) |
| Fabric suite | `./scripts/test-l.sh --fabric` | not run this round |
| npm audit | not run this round | last recorded in round 8: 0 for both packages |
