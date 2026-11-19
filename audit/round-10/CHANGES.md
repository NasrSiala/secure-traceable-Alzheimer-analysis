# Changes — round 10

| ID | Files | What changed | Verification |
|---|---|---|---|
| AUD-119 | `hw/rtl/sha256_core.vhd` | The header now says `busy` lasts 65 cycles and `done` is counted 66 cycles after the 16th word, matching `sha256_core_tb.vhd`. | Comment only. `test_sha256_core.py`: 35 passed, 1 skipped. |
| AUD-120 | `hw/sim/cocotb.mk`, `tests/scripts/test_sha256_core.py` | `PYTHONPATH` uses `;` when `OS` is `Windows_NT`. The structure test requires that separator. | Same pytest run. Cocotb itself was not executed. |
