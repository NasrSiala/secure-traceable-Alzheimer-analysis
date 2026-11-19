# Changes — round 11

| ID | Files | What changed | Verification |
|---|---|---|---|
| AUD-122 | `hw/sim/test_sha256.py`, `tests/scripts/test_sha256_core.py` | `put_word` now raises `word_valid` for one edge only after `word_ready` is already 1, then drops it. `run_block` counts busy the way cocotb samples it (64 edges still high, done 65 cycles after the accepting edge) and still returns 65. The structure test requires the words "16th word". | `py -3 -m pytest -q -o addopts= tests/scripts/test_sha256_core.py tests/scripts/test_sha256_padder.py`: 40 passed, 2 skipped. `ruff check` and `ruff format --check` clean. GHDL and cocotb are not installed, so the bench was not executed. |
