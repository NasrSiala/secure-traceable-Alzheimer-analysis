# Changes — round 13

| ID | Files | What changed | Verification |
|---|---|---|---|
| AUD-132 | `hw/ps_app/saam_cmd.c`, `hw/ps_app/saam_cmd_hostcheck.c` | Digest registers are stored big-endian. Length, CRC, version and `coef_id` stay little-endian. The host check sets `DIGEST0` to `0xBA7816BF` and requires the bytes `BA 78 16 BF`. | `gcc -Wall -Wextra -Werror` then `SAAM_CMD_HOSTCHECK PASSED`. UART and FIR pytest: 12 passed, 1 skipped. |
