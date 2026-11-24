# Audit report, round 8 — SAAMSTIAHF

Date: 2026-11-16 · Scope: the owner's uncommitted `l09-no-phi-guard` (T2.9) working tree, on top of the committed and pushed `l08-gateway-history-model-routes` @ `1c47ba6` (which round 7 audited and fixed). Earlier rounds: `audit/`, `audit/round-2/` to `audit/round-7/`. Tree audited: 2 modified tracked files and 6 new files (`INVENTORY.md`).

## 1. Summary

l09 adds the NFR-03 guard: `tests/integrity/phi_guard.py` judges the records that `GetCaseHistory` returns (exactly the 14 fields of the closed ARTIFACT schema, each value in its format, no name and no date of birth in the two free tokens, timestamps in the project era, diagnostics without a value). `gateway_history.py` is the `httpx` path to the gateway that plan l09 allows until `LedgerClient` (T2.7) exists. `fabric/gateway-serve.sh` serves the real `server.js` for the network tests. `test_no_phi_onchain.py` has 177 offline tests and 11 network tests. The guard rejects what it should: 40 of 46 mutations of the guard and its HTTP path are caught, and the six that were not point at test gaps, not at a defect in the guard.

Two things were really wrong: the fixture that serves the gateway left it running when Node is on the host (AUD-106), and the HTTP path went through `HTTP_PROXY` when the environment has one (AUD-110). Both are fixed and tested, on Windows and on real Linux.

| Severity | Count | IDs |
|---|---|---|
| Critical / High / Medium | 0 | |
| Low | 5 | AUD-106, AUD-107, AUD-108, AUD-110, AUD-111 |
| Info | 1 new, 6 carried over | AUD-109; AUD-095 to AUD-098, AUD-104, AUD-105 (rounds 6 and 7, unchanged) |

Decisions needed from the user: AUD-109 (what the guard may demand of `softwareVersion` and `modelVersion`; a stricter format means a decision on the on-chain schema, which AGENTS.md reserves). Nothing else blocks.

## 2. Coverage

The l08 commits (`fdaea2d`, `dd2223d`, `1c47ba6`) were audited in round 7 and did not change; they are `[=]` in `INVENTORY.md`. The 8 files of the l09 tree (2 modified, 6 new) were read in full, the 4 files of `tests/integrity/` line by line against the schema (`docs/specs/04-backend-schema.md` §5.2, `chaincode/provenance/src/artifact.ts`), `gateway-serve.sh` and its contract tests against `fabric/lib/gateway-run.sh` and `ledger-gateway/src/{server,settings}.ts`. The 177 offline tests were checked by mutation (§3), not only read. `PROGRESS.md` was checked against the counts of the baseline. After the fixes every changed file was read again (§6). Files that round 8 added: `tests/integrity/process_tree.py` and the tests of the fixes.

## 3. Baseline

See `BASELINE.md`: local suite exit 0 (Python 368 passed / 1 skipped, Jest 183 chaincode and 212 gateway), ruff, format and mypy clean. The 11 network tests were not run at the baseline. Four probes were run before any change; each one produced a finding or a table row:

- 46 mutations of the guard and of the HTTP path: 6 survive (AUD-108).
- `orphan-probe.sh` on real Linux: the gateway outlives a `SIGTERM` to the script (AUD-106).
- `probe_proxy.py`: the HTTP path fails behind a dead `HTTP_PROXY` (AUD-110).
- `probe_guard.py`: 9 of 18 values are not handled as the project's policy would (AUD-109).

## 4. Findings

### AUD-106 — Low — Correctness — the network fixture leaves the gateway running when Node is on the host
- **Location:** `tests/integrity/test_no_phi_onchain.py:742-746` (the `finally` of `live_gateway`: `process.terminate()` when the process is still running), `fabric/gateway-serve.sh:34` (`run_gateway_script start` is not the last process of a chain that a signal reaches)
- **Description:** `gateway-serve.sh` runs `npm run build` and `npm run start` as children of bash; the gateway is a grandchild. `Popen.terminate()` ends the script and nothing else. With host Node, `npm` and `node` keep running, with the wallet, the port 18080 and the token file loaded in memory. With the container branch the fixture's `docker rm -f` hides it, and that is the branch of this workstation (no Node on the PATH), so the owner's runs could not show it.
- **Evidence:** `audit/round-8/tools/orphan-probe.sh`, run on WSL2 Ubuntu with the real `gateway-serve.sh` and `gateway-run.sh` and a stub `npm` whose `run start` stays up: `serve script pid=33698, gateway pid=33705` → `SIGTERM` to the script → `RESULT: the gateway is still running after SIGTERM to the script (orphan)`. On Windows, `taskkill /F /T` does not fix it: `audit/round-8/tools/windows_tree_probe.py` → `taskkill /F /T : grandchild alive afterwards = True`, `job object : grandchild alive afterwards = False` (`windows-tree-probe.log`). The programs that Git Bash starts do not name the bash that started them as their parent (`Get-CimInstance Win32_Process`: the `sleep.exe` of the probe has a `ParentProcessId` that is no bash), so a walk down the tree misses them.
- **Root cause:** the fixture stops the process it started and assumes that stops what that process started. No part of the chain owns the gateway's lifetime: the script does not trap the signal, and the fixture does not address the group.
- **Impact:** after a run on a host with Node (the other members, the demo machine, a Linux CI), a gateway stays up holding port 18080. The next run's `node` fails with "address in use" and the fixture reports `the gateway stopped (exit 1)`; if the new one is slower to fail, the probe talks to the old gateway, whose tokens no longer match. The leftover process holds the Fabric wallet identities. Test infrastructure only; nothing reaches production.
- **Recommended fix:** start the script as the leader of its own process group on POSIX and signal the group; on Windows put the process in a job object and terminate the job. Keep it in one small helper and test it without Fabric.
- **Status:** Fixed. `tests/integrity/process_tree.py` (`ProcessTree`: `start_new_session` and `killpg` on POSIX, a job object through `ctypes` on Windows, `taskkill /T` only if the job cannot be made); the fixture uses it; `test_stopping_the_serve_process_stops_what_it_started` runs a script with a grandchild and checks that the grandchild is gone, without Fabric. It passes on Windows and on real Linux (WSL2, `killpg`). Three mutations of the fix fail the test (job never terminated, no job, only the script signalled: `mutations-fixes.log` P1 to P3); the `taskkill`-only attempt, which was the first version of the fix, failed this very test on Windows, which is how the job object came in. `gateway-serve.sh` header says how to stop it. Not verified: the Windows host-Node branch with a real `node.exe` (no Node on this host); the helper is checked with Git Bash children, which showed the failure of the tree walk.

### AUD-107 — Low — Docs/Test — the list of users of `gateway-run.sh` omits `gateway-serve.sh`, and the test that guards the list cannot see it
- **Location:** `fabric/lib/gateway-run.sh:2-7`, `tests/scripts/test_history_check_script.py:109-129`
- **Description:** `gateway-serve.sh` sources the library and is not named in its header. `test_the_check_scripts_share_one_dispatch` finds `fabric/*-check.sh`, and `gateway-serve.sh` does not end in `-check.sh`, so a copy of the dispatch in it would pass.
- **Evidence:** `grep -n "gateway-serve" fabric/lib/gateway-run.sh` finds nothing before the change. Same defect as AUD-093 and AUD-102 one increment later.
- **Root cause:** AUD-102 made the list follow the file *names*; the criterion that matters is "sources the library". A new script that is not a check script slips through the same way.
- **Impact:** low; the next script that sources the library and is not a check has the same two silent omissions.
- **Recommended fix:** find the scripts by what they do (`fabric/*.sh` that mention `lib/gateway-run.sh`), keep the `*-check.sh` names, and name `gateway-serve.sh` in the header.
- **Status:** Fixed. The header names the script; the test takes the union of `*-check.sh` and every `fabric/*.sh` that mentions the library, requires the six known names, and applies the same four assertions to each. Two mutations fail it: a library header without `gateway-serve.sh` (D1) and a new `fabric/zz-stray.sh` that sources the library and is not named (D2).

### AUD-108 — Low — Test — six mutations of the guard and of its HTTP path pass the 177 offline tests
- **Location:** `tests/integrity/phi_guard.py` (`docType` check, `TIMESTAMP_LAST_YEAR`, the key scan, the birth-word pattern, the title pattern), `tests/integrity/gateway_history.py` (`rstrip("/")`)
- **Description:** the tests do not pin six behaviours of the guard. The owner's own 19-mutation run closed two other holes the same way.
- **Evidence:** `audit/round-8/mutations-guard.log` (46 mutations, `tools/mutate_guard.py`): M01 `docType` accepted whatever its value; M10 `TIMESTAMP_LAST_YEAR = 9999` (only the lower bound of the era was tested); M14 the *key* of a field outside the schema no longer read for patterns (`ILLEGAL_FIELDS` has `"Jean Dupont"` and asserts only `unknown_field`); M25 the birth words (`dob`, `born`, `naissance`, `birth…`), which the date tests also trigger through a date; M28 the title pattern (`M. Martin`, `Mr. Dupont`: the other name patterns catch `Mme Martin` and `Dr Dupont` but not a title with a full stop); G07 `base_url.rstrip("/")` (a base URL with a trailing slash would send `//ledger/…`).
- **Root cause:** each test was written for the case the author had in mind; none was written for the pattern that only one line of code serves.
- **Impact:** a later edit that drops one of these lines keeps the suite green and weakens NFR-03. The guard is the net under the schema's one free string.
- **Recommended fix:** one test per surviving line: a wrong `docType`; a timestamp after 2099 and the two edges of the era; a name and a date used as a field name; each birth word alone in a free token; titles with a full stop; a trailing slash.
- **Status:** Fixed. 39 tests added to `test_no_phi_onchain.py` (177 → 216 offline); nothing was removed or changed in the existing ones except that `test_a_timestamp_far_from_the_project_era_is_detected` gained three values (it only gets stricter). The six mutations are now killed (`mutations-guard-after.log`); the other 40 still are.

### AUD-109 — Info — Test/Design — a name or a date written as a plain token passes the guard; the schema leaves the field open
- **Location:** `tests/integrity/phi_guard.py:77` (`_TOKEN`), `:93-102` (date patterns), `docs/specs/04-backend-schema.md:144-145` (`softwareVersion`, `modelVersion`: string, ≤ 64)
- **Description:** the chaincode bounds `softwareVersion` and `modelVersion` by length only. The guard accepts a value that is a technical token (`[A-Za-z0-9._+-]`, no space) and flags names and dates by pattern. What a pattern cannot tell from a version passes.
- **Evidence:** `audit/round-8/tools/probe_guard.py`: not flagged: `jean.dupont`, `dupont`, `JeanDupont`, `dupont.j` (names without a space, lower case or camel case); `12031975` (DDMMYYYY without a separator), `12-03-75` (two-digit year), `1890-03-12` (before 1900), `1975` and `1975-03` (year and month). Flagged, as the policy wants: names with a space or a hyphen between capitalised words, `1975-03-12`, `19750312`, `born1975`. Accepted, as they should be: `0.1.0`, `ecg-cnn-1.0.0`, `a1b2c3d`. A trailing newline also passes, because the guard's regexes end in `$`.
- **Root cause:** a free string cannot be proven free of identity by a pattern; the project's policy says "x.y.z" but neither the schema nor the chaincode enforces it, and `modelVersion` examples in the tests (`ecg-cnn-1.0.0`) are not x.y.z.
- **Impact:** the guard is a net, as the owner's decision row says ("Limite connue"). A writer that puts an unspaced name in `softwareVersion` is not caught. The pipeline writes the value, not a user, so the risk is a bug or a careless script, not an attack.
- **Recommended fix (decision needed):** either fix a version shape in the spec and the chaincode (`softwareVersion` and `modelVersion` as semantic versions, `modelVersion` as the registered model's `version`), which changes the on-chain schema (AGENTS.md: ask), then require the shape in the guard; or accept the residual risk and keep the guard as it is. Tightening the patterns alone would flag legitimate builds (`1.2.30` reads as a day, a month and a two-digit year).
- **Status:** Deferred (needs a decision of the spec owner). Nothing changed.

### AUD-110 — Low — Config/Privacy — the HTTP path of the guard goes through `HTTP_PROXY`
- **Location:** `tests/integrity/gateway_history.py:53-55` (`httpx.Client(transport=…, timeout=…)`, `trust_env` left at its default `True`)
- **Description:** with no transport given, httpx reads `HTTP_PROXY`, `ALL_PROXY` and `NO_PROXY` from the environment. A request to `http://127.0.0.1:18080` then goes to the proxy.
- **Evidence:** `audit/round-8/tools/probe_proxy.py`: a server on the loopback, `HTTP_PROXY=http://127.0.0.1:9` → `with HTTP_PROXY set to a dead port: LedgerAccessError: the gateway could not be reached` and the server saw 1 request (the one without the variable).
- **Root cause:** the default of the client suits calls to the internet; this client only calls a gateway that the test itself started on the loopback.
- **Impact:** on a machine with a proxy variable (a university or company network) the network tests fail with a message that blames the gateway, and when the proxy is reachable the `X-Agent-Token` and the synthetic records go to the proxy. The guard exists to keep data away from places it should not be.
- **Recommended fix:** `trust_env=False`.
- **Status:** Fixed (`gateway_history.py`, comment included). `test_the_gateway_is_called_directly_whatever_the_proxy_variables` starts a real server on the loopback, sets four proxy variables to a dead port and reads the history; mutation H1 (`trust_env=True`) fails it. The first version of the test bound port 0 and failed on the WSL2 kernel of this workstation (a kernel-assigned port refuses connections there: see §6); it now picks a free port and binds it by number, and passes on Windows and on Linux.

### AUD-111 — Low — Docs — `PROGRESS.md` no longer says that l08 is pushed, and its T2.9 counts are the ones before the audit
- **Location:** `PROGRESS.md:9` (the list of pushed increments stops at l07; the sentence that said l08 was pushed was in the "Tâche suivante" line that l09 replaced), `PROGRESS.md:20` (T2.9 proof row)
- **Description:** after l09's edit nothing in the header records l08 as committed and pushed. The T2.9 proof row counts 177 offline tests, 22 contract tests and 368 local tests; the audit adds 39 offline tests.
- **Evidence:** `git diff HEAD -- PROGRESS.md` (the line removed), the baseline counts.
- **Root cause:** one status line carries two facts (what is next, what is pushed), and the editor replaced the line.
- **Impact:** the next reader cannot tell from the header whether l08 left the machine.
- **Recommended fix:** list l08 among the pushed increments; add the post-audit counts to the proof row without rewriting the owner's text; add the round-8 row to "Problèmes".
- **Status:** Fixed (line 9, the proof row and a "Problèmes" row; the owner's sentences are intact).

## 5. Fix plan and order followed

AUD-106 first (the only one that leaves something running), then AUD-110 (privacy), AUD-108 (the tests that make the next edits safe), AUD-107, AUD-111. AUD-109 waits for a decision.

## 6. Verification

Run on the final tree, after the fixes (`final-test-l.log`, `live-integrity.log`, `mutations-*.log`, `linux-suite.log`, `npm-audit.log`).

| Check | Baseline | After the fixes |
|---|---|---|
| `bash scripts/test-l.sh` | exit 0; Python 368 passed, 1 skipped; Jest 183 and 212 | exit 0; Python **407 passed**, 1 skipped (+39 in `tests/integrity`); Jest 183 and 212 |
| `ruff check .`, `ruff format --check .`, `mypy tests` | pass, pass (29 files), pass (29 files) | pass, pass (95 files), pass (30 files) |
| `bash -n` on every `.sh` (`fabric/`, `fabric/lib/`, `scripts/`, `audit/round-8/tools/`) | pass | pass |
| `git diff --check` | not run | exit 0 (CRLF notices only) |
| `npm audit` (gateway, chaincode), pinned Node image | not run (no JavaScript change) | 0 vulnerabilities, 0 vulnerabilities |
| Mutations of the guard and its HTTP path (46) | 40 killed, 6 survive | **46 killed**, 0 survive (`mutations-guard-final.log`) |
| Mutations of the fixes (6) | n/a | 6 of 6 killed: `trust_env` back to `True`, job never terminated, no job (`taskkill /T` only), only the script signalled, header without `gateway-serve.sh`, a new unnamed script (`mutations-fixes.log`) |
| The 11 network tests, `pytest tests/integrity -m fabric -o addopts=` (Windows host, container branch of `gateway-serve.sh`) | not run | **11 passed in 479 s** (network start, enrolment, gateway behind a token file, 7-artifact histories, refused illegal fields, patterns written in `softwareVersion` found, no token or payload in the diagnostics). Afterwards: no `saam-medtrace` container, no wallet, no runtime directory, no token directory in `%TEMP%`, no listener on 18080 |
| Real Linux (WSL2 Ubuntu 22.04, Python 3.10), `tests/integrity`, `test_gateway_serve_script.py`, `test_history_check_script.py` | n/a | 253 passed (includes the `killpg` branch of `ProcessTree` and the new dispatch test) |
| Real Linux, the whole non-Fabric suite (`tests`, `linux-suite.log`) | n/a | 406 passed, 2 failed: `test_check_ports_reports_a_busy_port` and `test_board_flag_runs_no_board_tests_and_does_not_open_a_device` (it re-runs the first). Environment, not a defect of l09: a server bound to a kernel-assigned port (port 0) refuses connections on this WSL2 kernel (`uname -r` = 6.6.87.2-microsoft-standard-WSL2), while the same server on a port given by number answers |

The network run started before the last edit of the proxy test (`apply_fixes_3.py`, a port choice in one test that does not use the network); the 216 offline tests, the final local suite and the 46 mutations ran after it.

**Re-audit.** Every file the audit changed or added was read again: `process_tree.py`, the new and changed parts of `test_no_phi_onchain.py`, `gateway_history.py`, the header of `gateway-run.sh` and of `gateway-serve.sh`, `test_history_check_script.py`, `PROGRESS.md`. Two of the audit's own first versions failed their tests and were replaced, which is what the tests are for: the stop helper first used `taskkill /F /T`, which leaves the grandchild alive on Windows (`windows-tree-probe.log`), so it became a job object; the proxy test first bound port 0 and failed on the WSL2 kernel, so it picks a free port and binds it by number. No new finding came out of the re-read. One limit of the job object is written in `process_tree.py`: it is assigned right after `Popen` returns, and a child created before that would escape it; `gateway-serve.sh` has not started one by then.

**Not verified.**
- The host-Node branch of `gateway-serve.sh` with a real `node.exe` (this host has no Node on the PATH): the Windows part of `ProcessTree` is checked with the processes Git Bash starts, which is where `taskkill /T` failed. A second workstation or the demo machine with Node would close it (A-02.3, Q-03).
- A native Linux host (WSL2 only), and the 13 older Fabric tests (`test_network`, `test_node_fallback`, …): nothing they use changed, the suite takes 50 to 80 minutes, and the owner ran it on this tree (`PROGRESS.md`: 22 passed and 2 infrastructure failures that passed alone).
- The failure branches of the live scripts against a gateway that misbehaves.

## 7. Unresolved

| ID | Severity | Status | Why | Risk of leaving it | What is needed |
|---|---|---|---|---|---|
| AUD-109 | Info | Deferred | a stricter guard needs a version shape in the on-chain schema, which AGENTS.md reserves; tightening the patterns alone flags legitimate versions | an unspaced name or an odd date written in `softwareVersion` or `modelVersion` is not caught; the pipeline is the only writer | decision of the spec owner: a semantic-version shape for both fields, or acceptance of the residual risk |
| AUD-104 | Info | Open (round 7) | copied `report`, `logFailure`, `codeOf` in the check programs | none today | four live programs to re-prove if merged |
| AUD-105 | Info | Open (round 7) | the contract tests of the check scripts exist in four files | none today | the owner's decision to merge them (renames tests) |
| AUD-095 to AUD-098 | Info | Open (round 6) | decisions of the spec owner or of B | see round 6 | unchanged |

Observed, no defect:
- `test_the_http_path_is_the_approved_one_until_ledgerclient_exists` fails on purpose when `saam.ledger` appears (T2.7). The merge request of B will turn the default suite red until the guard is switched to `LedgerClient`; that is the plan's wording ("Mis à jour : quand T2.7 arrive…").
- `uv run pytest tests/integrity -q` (AGENTS.md) runs the 216 offline tests; the 11 network tests need `./scripts/test-l.sh --fabric` or `pytest tests/integrity -m fabric -o addopts=`.
- `httpx` is in the TRD §18 list; there is no `pyproject.toml` or `uv.lock` yet (T1.1, B), so the offline suite needs `httpx` installed by hand (WSL2 needed its wheels).
- `fabric/gateway-serve.sh` is executable on disk and untracked: stage it with `git add --chmod=+x` (the host has `core.fileMode=false`).
