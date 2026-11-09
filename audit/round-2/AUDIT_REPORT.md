# Codebase Audit Report, round 2 — SAAMSTIAHF

Date: 2026-11-09 · Branch audited: `l01-fabric-network` @ `8f475d4` plus the uncommitted `l02-agent-identities` (T1.4) working tree · Auditor: Claude Code (codebase-audit skill)

Round 1 (`audit/AUDIT_REPORT.md`, AUD-001 … AUD-026) covered the spec suite and the T1.3 Fabric network. This round covers what changed since: the T1.4 work (enrollment of nine identities, a CCAAS demo chaincode, a minimal gateway, the `spike` profile in Compose, `test_identities.py`) and re-verifies everything else. Finding IDs continue from AUD-027.

## 1. Executive summary

The repository is a spec suite plus the first two increments of the L role: an isolated Fabric 2.5 test network, its test harness, and now identity enrollment with an attribute-reading demo chaincode. There is no application code yet. The T1.4 work is functionally sound: the baseline Fabric suite passes (4 passed, including a real transaction accepted for `agent-ingestion` and refused for `verifier`) and no secret reaches git or the logs. The problems are around it: the new scripts cannot be safely re-run, a failed or interrupted enrollment can leave the test network impossible to stop, the documented `./…` entry points do not work on Linux/macOS, and the pinned Fabric JavaScript packages carry known high-severity advisories because `fabric-shim` is two patch releases behind `fabric-contract-api`.

| Severity | Found | Fixed | Workaround | Deferred | Won't fix | Could not verify |
|---|---|---|---|---|---|---|
| Critical | 0 | 0 | 0 | 0 | 0 | 0 |
| High | 1 | 1 | 0 | 0 | 0 | 0 |
| Medium | 6 | 6 | 0 | 0 | 0 | 0 |
| Low | 9 | 9 | 0 | 0 | 0 | 0 |
| Info | 5 | 2 | 0 | 0 | 2 | 1 |

21 findings (AUD-027 … AUD-047): 18 fixed and verified, 2 won't fix, 1 could not verify. AUD-044 came from Node appearing on the host mid-audit; AUD-045, AUD-046 and AUD-047 came from running the suite on real Linux (WSL2 Ubuntu) after the first fixes, which also reproduced and closed AUD-041.

Top risks (all fixed):
1. AUD-046 — on Linux, `network.sh stop`/`start` fail after the first start (root-owned files left by containers), so the T1.3 "up and down 3 times" check and every later test fail. Found only by running on real Linux.
2. AUD-028 — a leftover build container makes `network.sh stop` fail (the new Compose services lacked the ownership label). Reproduced.
3. AUD-029 — `fabric/enroll-identities.sh` fails on its second run (two keys in a keystore). Reproduced.
4. AUD-030 — `@grpc/grpc-js` 1.8.15 / 1.12.4 and `protobufjs` 6.11.6 carried high-severity advisories because `fabric-shim` was two patch releases behind `fabric-contract-api`.
5. AUD-027 / AUD-045 — scripts committed without the executable bit; `test-l.sh` found no pytest on stock Ubuntu.

## 2. Scope and coverage

- Stack: Bash, Docker Compose, Hyperledger Fabric 2.5.16 (CCAAS chaincode), TypeScript (Node 20 in the pinned image; Node 22 on the Windows host since mid-audit), Python 3 + pytest/ruff/mypy for the harness.
- Files in inventory: 66 · Read in full this round: 25 (all changed or new files) · Unchanged since round 1 and re-verified: 37 · Excluded: 4 (`audit/round-2/INVENTORY.md`).
- Exclusions: binary `.pptx`, local `.venv/`, generated/ignored directories, one empty untracked directory.
- Not verifiable: macOS, a native Linux Docker Engine (the Linux run used WSL2 Ubuntu against Docker Desktop's engine), `shellcheck`, a second workstation.

## 3. Baseline (before changes)

See `audit/round-2/BASELINE.md`. Summary: local suite 19 passed / 1 skipped; Fabric suite 4 passed (617 s); `ruff check` and `mypy tests` clean; `ruff format --check` fails on 2 files (new); host TypeScript tests not run (no Node); advisories found in both lockfiles.

## 4. Findings

### AUD-046 — On Linux, the network cannot be restarted: containers leave root-owned files the host user cannot delete

- **Severity:** High
- **Category:** Correctness
- **Location:** `fabric/network.sh` (`remove_generated`); `fabric/scripts/enroll-identities.sh` (wallet); `fabric/enroll-identities.sh` (`build_node_package`); `fabric/spike-submit.sh`; `ledger-gateway/src/spike-submit.ts` (TLS CA path)
- **Description:** every Fabric container runs as root and writes into bind-mounted directories of the checkout (`organizations/`, `channel-artifacts/`, `wallet/`, and `node_modules/` and `dist/` of both Node packages). On Windows/macOS Docker Desktop maps ownership, so nothing shows. On Linux the files stay owned by root: `network.sh stop` and the start-up cleanup fail on `rm -rf`, the host user cannot read its own wallet, and cannot run or delete `node_modules`.
- **Evidence:** run on real Linux (WSL2 Ubuntu 22.04, ext4, uid 1000, same Docker engine; `audit/tools/linux_check.sh`): `scripts/test-l.sh --fabric` → 5 failed, 1 error. First failure `cycle 1 start failed with exit 1 … rm: cannot remove 'organizations/peerOrganizations/org2.example.com/users': Permission denied … error: Could not remove /home/msi_user/saam/fabric/organizations.` The T1.3 definition of done (up and down 3 times) therefore fails on Linux; the leftover state made every later test fail. `ls -ld` showed `organizations/peerOrganizations` and `…/peers` as `root root`, mode 700 for `peers`, so the host default of `spike-submit.ts` (`organizations/…/tls/ca.crt`) was also unreadable; and `ledger-gateway/node_modules` was root-owned after the enrollment build.
- **Root cause:** the scripts assume the host user can manage whatever a root container writes. That holds only where the file-sharing layer remaps ownership.
- **Impact:** on a Linux workstation or CI runner the Fabric test network cannot be torn down or restarted after the first `start`, identities cannot be used from the host, and `npm` fails in the checkout. This is the second-workstation test of T1.3 (A-02.3), and the CI the TRD plans on GitHub Actions.
- **Recommended fix:** (1) delete the generated directories with a root container when the host cannot, through the same compose file as every other service; (2) hand the wallet files and the Node build outputs to the owner of the directory they are written into; (3) publish the peer's TLS CA certificate in the wallet so host tools never read `organizations/`.
- **Status:** Fixed
- **Fix applied:** `compose.yaml`: new `cleaner` service (profile `tools`, `network_mode: none`, mounts `..:/work/fabric`) so cleaning does not recreate the project network. `network.sh`: `remove_generated` tries the host `rm`, then deletes the four generated directories in the root container, then verifies (5 retries kept for Windows file locks). `scripts/enroll-identities.sh`: wallet files are given to the owner of `/work/wallet` (0:0 on Docker Desktop: skipped) and the peer's TLS CA certificate is published as `wallet/peer0-org1-tls-ca.crt`; `spike` mounts only the wallet; `spike-submit.ts` and `spike-submit.sh` use it. `enroll-identities.sh`: `node_modules` and `dist` handed back to the checkout owner after the build. New tests: four unit tests of `remove_generated` with `rm` and `compose` faked (host can delete, falls back to the container, container fails, directory survives), `test_cleaner_service_removes_generated_files_without_a_network`, and in `test_identities.py` an assertion that the wallet, `node_modules` and `dist` of both packages belong to the current user (active when `os.getuid` exists and is not root). **Red/green on Linux:** before, 5 failed + 1 error (above); after, `pytest -m fabric` on WSL Ubuntu → 8 passed, no root-owned file left.

### AUD-027 — Shell scripts are committed without the executable bit

- **Severity:** Medium
- **Category:** Config
- **Location:** git index for `fabric/network.sh`, `fabric/scripts/{enroll,join-channel,start-ca}.sh`, `scripts/test-l.sh`; the new `fabric/enroll-identities.sh`, `fabric/spike-submit.sh`, `fabric/scripts/{enroll-identities,deploy-identity-spike}.sh`; `fabric/enroll-identities.sh:189-192`
- **Description:** All scripts are mode `100644` in Git. The project's documented commands (`./fabric/network.sh up`, `./scripts/test-l.sh`, AGENTS.md "Commandes") and the host enrollment script's own `./network.sh stop|start|status` calls need the executable bit.
- **Evidence:** `git ls-files -s fabric scripts` prints `100644` for every `.sh`; `git config core.fileMode` is `false` (Windows), so Git never records the bit from this checkout. The working-tree listing shows `-rwxr-xr-x` only because MSYS fakes it.
- **Root cause:** Developed on Windows with `core.fileMode=false`; nothing sets or checks the index mode.
- **Impact:** On Linux/macOS (the second-workstation test A-02.3, CI runners) `./fabric/network.sh` and `./scripts/test-l.sh` fail with "Permission denied"; the enrollment would also fail on its internal `./network.sh` calls. Tests pass here only because they invoke `bash <script>`.
- **Recommended fix:** `git update-index --chmod=+x` for tracked scripts (and `git add --chmod=+x` when staging the new ones); call `bash ./network.sh` inside the script; add a test that every staged `*.sh` is `100755`.
- **Status:** Fixed
- **Fix applied:** Index modes set to `100755` for the 5 tracked scripts and `audit/tools/verify_schema_patch.sh` (`git update-index --cacheinfo`, content left unstaged: nothing of the T1.4 work is staged). `fabric/enroll-identities.sh` calls `bash ./network.sh`. New tests: `test_shell_scripts_are_executable_in_the_git_index`, `test_host_script_calls_the_network_script_through_bash`. **Action for whoever stages T1.4:** `git add --chmod=+x fabric/enroll-identities.sh fabric/spike-submit.sh fabric/scripts/enroll-identities.sh fabric/scripts/deploy-identity-spike.sh`; the first test fails if they are added as `100644`. Checked on this host only (Linux/macOS: Could not verify).

### AUD-028 — A leftover one-off build container makes `network.sh stop` and `start` fail

- **Severity:** Medium
- **Category:** Config
- **Location:** `fabric/compose/compose.yaml:271-292` (`cc-build`, `gw-build`), `:343-361` (`spike`); `fabric/network.sh:307-314, 344-358`
- **Description:** Every other service carries the label `saam.network: medtrace`, which is the ownership marker that `remove_labeled_containers` and the test fixtures use. The three new one-off services (`cc-build`, `gw-build`, `spike`) have no label.
- **Evidence:** reproduction: `docker compose … --profile spike run -d gw-build -lc "sleep 600"` (what an interrupted `npm ci` leaves behind), then `fabric/network.sh stop` → `Error response from daemon: error while removing network: network saam-medtrace has active endpoints (name:"saam-medtrace-gw-build-run-…")`, exit 1, container and network remain. `docker ps -a --format '{{.Label "saam.network"}}'` is empty for that container. `compose down` does not remove one-off containers.
- **Root cause:** New services were added without following the labelling rule that the stop path depends on (`cmd_stop` → `remove_labeled_containers` → `docker network rm`).
- **Impact:** Ctrl-C (or a crash) during `npm ci` in `fabric/enroll-identities.sh` leaves the test network impossible to stop; `start` begins with `cmd_stop`, so it fails too until the container is removed by hand. The test fixtures would also count the container as "foreign".
- **Recommended fix:** add the same labels (`saam.network: medtrace`, `saam.role: …`) to `cc-build`, `gw-build` and `spike`; add a contract test that every service in Compose carries the ownership label.
- **Status:** Fixed
- **Fix applied:** `compose.yaml`: `saam.network` + `saam.role` labels on `cc-build`, `gw-build`, `spike`. New tests: static `test_every_compose_service_carries_the_ownership_label`; live `test_stop_removes_a_build_container_left_by_an_interrupted_enrollment` (red without the label: `cleanup stop failed with exit 1 … active endpoints`, green with it).

### AUD-029 — Identity enrollment cannot be repeated on a running network

- **Severity:** Medium
- **Category:** Correctness
- **Location:** `fabric/scripts/enroll-identities.sh:68-100` (`enroll_client`, `copy_one` at lines 96-97)
- **Description:** `register_identity` tolerates "already registered", so the script is written to be re-runnable, but `enroll_client` enrolls into the same `msp` directory each time. `fabric-ca-client` adds a new key under `keystore/` on every enrollment, and `copy_one` demands exactly one match.
- **Evidence:** live run: after a successful `fabric/enroll-identities.sh`, a second run ends with `Enrolling agent-ingestion` / `Expected one file matching …/agent-ingestion@org1.example.com/msp/keystore/*, found 2.`, exit 1; the keystore holds 2 files.
- **Root cause:** stale generated key material is never cleared before a new enrollment.
- **Impact:** any failure after the enrollment step (npm registry down, chaincode build error) forces a full `stop` + `start` (several minutes) before the next attempt; the retry path the script advertises does not work.
- **Recommended fix:** remove the identity's generated `msp` directory before enrolling; add a test that runs the enrollment twice and still gets an accepted transaction.
- **Status:** Fixed
- **Fix applied:** `fabric/scripts/enroll-identities.sh`: the identity's `msp` directory is removed before each enrollment. `test_identities.py` now runs the whole enrollment a second time on the live network, checks every certificate again and submits another transaction as `agent-ingestion`. Passed in the Fabric suite.

### AUD-030 — Pinned Fabric JavaScript packages carry high-severity advisories; shim and contract API are out of step

- **Severity:** Medium
- **Category:** Dependency
- **Location:** `chaincode/provenance/package.json:12-14`, `chaincode/provenance/package-lock.json`; `ledger-gateway/package.json:11`
- **Description:** `fabric-shim` is pinned to 2.5.5 while `fabric-contract-api` is 2.5.8. `fabric-shim@2.5.5` depends on exactly `fabric-contract-api@2.5.5`, `fabric-shim-api@2.5.5` and `@grpc/grpc-js@1.8.15`.
- **Evidence:** the lockfile holds two copies of `fabric-contract-api` (2.5.8 top level, 2.5.5 under `fabric-shim`), two of `fabric-shim-api`, three of `reflect-metadata` (0.2.2, 0.1.14 ×2), `@grpc/grpc-js` 1.8.15 and `protobufjs` 6.11.6. The npm advisory API reports, for 1.8.15: GHSA-5375-pq7m-f5r2 and GHSA-99f4-grh7-6pcq (malformed request/compressed message crash), GHSA-m9gg-hp2v-232j (high), GHSA-7v5v-9h63-cj86, GHSA-f596-whhp-79r4; for `protobufjs` 6.11.6: five high (e.g. GHSA-66ff-xgx4-vchm code injection, GHSA-685m-2w69-288q unbounded recursion). The gateway's `@grpc/grpc-js` 1.12.4 is in the range of GHSA-5375, GHSA-99f4 and GHSA-m9gg (fixed in 1.12.7 / 1.13.6). `fabric-shim@2.5.8` depends on `@grpc/grpc-js@^1.11.0`.
- **Root cause:** the shim was pinned one release set behind the contract API; the exact transitive pin on an old gRPC comes from that release. PROGRESS records the advisories as accepted, but a same-major bump removes them.
- **Impact:** the CCAAS chaincode server listens on the Docker network and is reachable by anything on it; a crafted request can crash it (denial of service). Test network only today, but l04 builds the real chaincode on the same pins. The duplicated `fabric-contract-api` means the `Contract` class the code extends and the one the shim uses are different module instances.
- **Recommended fix:** pin `fabric-shim` and `fabric-contract-api` to 2.5.8 and `@grpc/grpc-js` (gateway) to a patched 1.x (1.14.7); regenerate the lockfiles; re-run the Fabric suite. No `npm audit fix --force`, no major bump.
- **Status:** Fixed
- **Fix applied:** `chaincode/provenance/package.json`: `fabric-shim` 2.5.8 (= `fabric-contract-api` 2.5.8), `reflect-metadata` 0.1.14 (the release the Fabric libraries use); `ledger-gateway/package.json`: `@grpc/grpc-js` 1.14.7. Lockfiles regenerated in the pinned Node image: one copy each of the Fabric packages and of `@grpc/grpc-js` (1.14.7), `protobufjs` 7.6.6. `npm audit` on both packages: found 0 vulnerabilities (advisory API also empty). New tests: exact pins, lock in sync with `package.json`, one release/one copy, gRPC floor 1.13.6. Fabric suite passed with the new versions.

### AUD-044 — `npm test` cannot pass on a host with Node (Linux-built `node_modules`, no install step)

- **Severity:** Medium
- **Category:** Test
- **Location:** `scripts/test-l.sh:89-103` (`run_npm_test`); `chaincode/provenance/package.json:7-8`; `ledger-gateway/package.json:7-8`
- **Description:** Node 22.17.0 appeared on the host PATH while this audit was running (the baseline was taken without it). `scripts/test-l.sh` then runs `npm test` on the host, where `tsc` is "not recognized": `node_modules` had been installed by the Linux container into the bind-mounted package directory, and its `.bin/tsc` is a symlink that Windows npm cannot run. A fresh clone with Node has no `node_modules` at all, and `npm test` fails there too.
- **Evidence:** `bash scripts/test-l.sh --fabric` → `> tsc --noEmit` / `'tsc' n'est pas reconnu en tant que commande interne ou externe`, exit 1 after the 36 local pytest tests; the Fabric part never ran. `ls -la chaincode/provenance/node_modules/.bin/tsc` → symlink to `../typescript/bin/tsc`.
- **Root cause:** the package scripts depend on npm's `.bin` shims, which are platform-specific, while the enrollment shares one `node_modules` between a Linux container and the host; and the runner assumes dependencies are already installed.
- **Impact:** the L suite entry point is red (exit 1) on any Windows host that has Node and has run the enrollment, and on any fresh clone with Node; the Fabric tests behind it are never reached.
- **Recommended fix:** call the compiler as `node node_modules/typescript/bin/tsc` (works for modules installed on either side), and let `run_npm_test` run `npm ci --ignore-scripts` when `node_modules` is missing.
- **Status:** Fixed
- **Fix applied:** `package.json` (both): `build`/`test` call `node node_modules/typescript/bin/tsc`; `scripts/test-l.sh` `run_npm_test` runs `npm ci --ignore-scripts` when `node_modules` is missing. Verified: `bash scripts/test-l.sh` → 38 passed, both packages type-check on the host with the container-built modules; after deleting `ledger-gateway/node_modules` the script installed (0 vulnerabilities) and passed. Test: `test_npm_scripts_run_typescript_through_node`.

### AUD-045 — `scripts/test-l.sh` finds no pytest on stock Linux (`python3` only)

- **Severity:** Medium
- **Category:** Config
- **Location:** `scripts/test-l.sh` (`select_pytest`)
- **Description:** the script looked for `python` and `py -3` only. Ubuntu ships `python3` and no `python`.
- **Evidence:** on WSL Ubuntu with pytest importable by `python3`: `./scripts/test-l.sh` → `pytest is not available. Install it, or add the project pyproject.toml so uv can run it.`, exit 3. `fabric/network.sh` already tries `python3`, `python`, `py -3` (round 1, AUD-007).
- **Root cause:** the interpreter lookup was written on Windows and never run elsewhere; the same lookup was fixed in `network.sh` but not copied here.
- **Impact:** the documented entry point of the L suite does not start on Linux, including CI runners without `uv`.
- **Recommended fix:** same candidate order as `network.sh`: `python3`, `python`, `py -3`.
- **Status:** Fixed
- **Fix applied:** `select_pytest` tries `python3`, `python`, then `py -3`. Tests with the interpreters replaced by shell functions: `python3` alone is found, fallback to `python` then `py -3`, none → exit 3.

### AUD-031 — The chaincode commit check in `deploy-identity-spike.sh` is wrong in both directions

- **Severity:** Low
- **Category:** Correctness
- **Location:** `fabric/scripts/deploy-identity-spike.sh:94-111` (also install/approve error handling, lines 38-50 and 68-82)
- **Description:** a failed `peer lifecycle chaincode commit` is ignored if its output merely contains the string `identity-spike`. The intent is an idempotent re-run, but the real "already committed" error does not contain that string.
- **Evidence:** live probes in the `tools` container: committing sequence 1 again fails with `requested sequence is 1, but new definition must be sequence 2` (0 occurrences of `identity-spike`, so the script would exit 1 on a re-run); an unapproved sequence fails with `chaincode definition not agreed to by this org (Org1MSP)` (also not matched). Any failure that does name the chaincode (for example `namespace identity-spike is not defined`) would be reported as success. `peer lifecycle chaincode querycommitted` returns 0 with the definition when committed and 1 (`namespace … is not defined`) otherwise. The install and approve steps hide their output and print only a fixed message, so the cause of a failure is lost. PROGRESS "Trouvé, non construit" already notes the weakness.
- **Root cause:** the success condition is inferred from error text instead of being checked against the ledger.
- **Impact:** re-running the deployment fails; a real commit failure could be reported as success and surface later as a confusing invocation error.
- **Recommended fix:** commit only if `querycommitted` says the definition is absent, treat any commit failure as an error (print the last lines of the peer output), and verify with `querycommitted` afterwards.
- **Status:** Fixed
- **Fix applied:** `deploy-identity-spike.sh` rewritten around the ledger state: `calculatepackageid`, `querycommitted` before and after, approved package identifier checked on re-run, install/approve/commit failures print the last lines of the peer output. `enroll-identities.sh`: reproducible package archives (`mtime=0`, same bytes and identifier on each run; verified by building twice 2 s apart) and no silent exit when no identifier is printed. Covered by the second-enrollment step of `test_identities.py` (log contains "already committed") and `test_deploy_script_checks_the_ledger_not_the_error_text`, `test_chaincode_packages_are_reproducible_archives`. The matching row of PROGRESS "Trouvé, non construit" is removed.

### AUD-032 — `npm run spike:submit` on a host with Node can never succeed with its defaults

- **Severity:** Low
- **Category:** Correctness
- **Location:** `ledger-gateway/src/spike-submit.ts:11-13, 29-31`; `fabric/spike-submit.sh:15-19`
- **Description:** the plan (l02) names `npm run spike:submit` as the entry point. On the host path, `PEER_TLS_CERT` has no default and is never exported by `spike-submit.sh`, so the program throws `PEER_TLS_CERT is required`. The default `PEER_ENDPOINT` is `127.0.0.1:18051`, but the peer's TLS certificate only lists `peer0.org1.example.com`, `localhost` and `saam-medtrace-peer0-org1` as names (`fabric/scripts/enroll.sh:117-119`), so certificate verification would fail on the IP.
- **Evidence:** static reading of the two files and of the requested certificate names. The Docker path used by the tests sets all of `WALLET_DIR`, `PEER_ENDPOINT` and `PEER_TLS_CERT` in Compose, so it works. The host path is unreachable here (no Node on this host).
- **Root cause:** only the container path was exercised.
- **Impact:** a teammate with Node installed gets an error or a TLS failure instead of a transaction.
- **Recommended fix:** default `PEER_ENDPOINT` to `localhost:18051` and `PEER_TLS_CERT` to the Org1 peer's TLS CA under `fabric/organizations/…`, both overridable.
- **Status:** Fixed
- **Fix applied:** Host defaults `localhost:18051` and the peer's TLS CA certificate read from the wallet (`wallet/peer0-org1-tls-ca.crt`, published by the enrollment) because `organizations/` is root-only on Linux (AUD-046); `spike-submit.sh` stops early with `no wallet` when it is absent. Test: `test_spike_submit_defaults_work_from_a_host_with_node`; the host-Node path is exercised by the Windows Fabric suite.

### AUD-033 — The `spike` container mounts the whole `organizations` tree

- **Severity:** Low
- **Category:** Security
- **Location:** `fabric/compose/compose.yaml:350` (`../organizations:/organizations:ro`)
- **Description:** the spike only needs one file, the Org1 peer's TLS CA certificate, but receives the CA server keys, admin MSPs and all TLS private keys, in a container that runs `npm run` (third-party code).
- **Root cause:** convenience mount.
- **Impact:** low on a throwaway test network, but it breaks the least-privilege rule the TRD states for the wallet ("monté en lecture seule dans `ledger-gateway` uniquement") and copies a pattern l05 may inherit.
- **Recommended fix:** bind-mount only `…/peer0.org1.example.com/tls/ca.crt` read-only and point `PEER_TLS_CERT` at it.
- **Status:** Fixed
- **Fix applied:** `spike` mounts only the wallet read-only (identities plus the public TLS CA certificate); running chaincode services mount their package read-only. Tests: `test_spike_container_does_not_see_the_organizations_tree`, `test_running_chaincode_services_mount_their_source_read_only`.

### AUD-034 — The build step bypasses the lockfile and runs install scripts on the Fabric network

- **Severity:** Low
- **Category:** Dependency
- **Location:** `fabric/enroll-identities.sh:89-96`, `fabric/compose/compose.yaml:271-292`
- **Description:** `npm install --package-lock-only && npm ci && npx tsc` re-resolves the lock before `npm ci`, so a `package.json`/lock mismatch is silently "fixed" instead of failing, and the lock file in the working tree can change on every enrollment. Dependency lifecycle scripts run inside a container attached to the Fabric network. `npx tsc` can fetch a package if the local binary is missing.
- **Root cause:** the lock was generated by the same command that builds.
- **Impact:** non-reproducible builds; supply-chain exposure during `npm ci`.
- **Recommended fix:** `npm ci --ignore-scripts && npm run build` (lock files are now committed content; a mismatch must fail).
- **Status:** Fixed
- **Fix applied:** `build_node_package` runs `npm ci --ignore-scripts && npm run build`. Test: `test_build_uses_the_lockfile_and_skips_install_scripts`.

### AUD-035 — `node:20-bookworm` is a floating tag

- **Severity:** Low
- **Category:** Config
- **Location:** `fabric/compose/compose.yaml:272, 283, 294, 319, 344`
- **Description:** every Fabric image is pinned to an exact version (`2.5.16`, `1.5.17`) and the TRD requires pinned versions; the five Node services use a moving tag, and `test_compose_pins_fabric_25_leveldb_and_isolated_names` does not look at them.
- **Evidence:** local image is Node 20.20.2, digest `sha256:8f693eaa…c01c9ba5`.
- **Root cause:** pins were added for the Fabric images only.
- **Impact:** a pull could change the Node patch release under the build and the chaincode runtime.
- **Recommended fix:** `node:20.20.2-bookworm@sha256:<digest>` for all five services; extend the contract test so no service image is unpinned or `latest`.
- **Status:** Fixed
- **Fix applied:** All five Node services use `node:20.20.2-bookworm@sha256:8f693eaa…c01c9ba5` (the image already on this host, so nothing is pulled). Test: `test_every_compose_image_is_pinned`.

### AUD-036 — `ruff format --check` fails on two test files

- **Severity:** Low
- **Category:** Test
- **Location:** `tests/fabric/test_identities.py:101-147`, `tests/fabric/test_network.py:238-244`
- **Description:** the formatter would rewrite over-long lines in files added or edited for T1.4. Round 1 ended with the format check clean, and the L-plan verification list includes it.
- **Evidence:** `ruff format --check .` → `2 files would be reformatted`.
- **Impact:** CI format gate (TRD §17) would fail.
- **Recommended fix:** run `ruff format` on the two files (layout only).
- **Status:** Fixed
- **Fix applied:** `ruff format tests`; layout only, no assertion changed. `ruff format --check .` → 37 files already formatted.

### AUD-037 — `scripts/test-l.sh` stays green without type-checking any TypeScript on a host without Node

- **Severity:** Low
- **Category:** Test
- **Location:** `scripts/test-l.sh:98-101`
- **Description:** when `node` is not on PATH the script prints "was not run on the host" and continues with exit 0, so on this machine the "local suite" never type-checks the chaincode or the gateway (the access-control rule lives in the chaincode). The TypeScript is compiled only by `--fabric` (through the enrollment build).
- **Evidence:** baseline output: `node is not on PATH; chaincode/provenance npm test was not run on the host.` twice, then exit 0. PROGRESS "Problèmes" records this as accepted until T1.1 provides Node 20.
- **Root cause:** deliberate, documented trade-off (the suite is described as needing no network).
- **Impact:** a TypeScript error can be committed without any local signal on this host. CI (Linux, Node) will catch it once it exists.
- **Recommended fix:** none now; once T1.1 lands, make `test-l.sh` fail instead of skip when `package.json` exists and Node is missing, or run `npm test` in the pinned Node image.
- **Status:** Fixed
- **Fix applied:** `run_npm_test` order: host Node (installs with `npm ci --ignore-scripts` if `node_modules` is missing); else the pinned Node image from `compose.yaml` with the package mounted read-only and copied aside (nothing is written to the checkout, and the container carries the `saam.network=medtrace` label); else exit 3 with an explicit message. `SAAM_TEST_SKIP_NODE=1` skips knowingly and prints `SKIPPED:`. The script now has a `main` guard so tests can source it. Tests: no Node and no Docker → exit 3; opt-out → `SKIPPED`; node image read from Compose and pinned; sourcing runs nothing; `--help` documents the opt-out; live (Docker) tests that the container run passes for both packages without touching the checkout and fails with `error TS2322` on an injected type error. Verified on Windows (Node hidden from PATH), and on Linux where the host has no Node.

### AUD-038 — The Node dependencies in use are not all in the TRD §18 list

- **Severity:** Low
- **Category:** Docs
- **Location:** `docs/specs/02-trd.md:262` vs `chaincode/provenance/package.json:11-19`, `ledger-gateway/package.json:10-17`
- **Description:** TRD §18 lists, for Node, `fabric-contract-api, fabric-shim, @hyperledger/fabric-gateway, @grpc/grpc-js, fastify, pino`. The T1.4 packages also use `reflect-metadata` (required by the contract decorators), `typescript` and `@types/node` (the build). AGENTS.md says to stop and ask when a dependency absent from §18 seems necessary; the plan also mentions Jest and eslint, equally absent.
- **Root cause:** §18 lists runtime libraries only, not the TypeScript toolchain.
- **Impact:** low; all are standard, permissively licensed and required by the stack the TRD chose. The rule exists so the team decides dependencies explicitly.
- **Recommended fix:** a documentation patch to TRD §18 ("Node, outillage : typescript, @types/node, reflect-metadata, jest, eslint") with version bump and CHANGELOG entry. That is a spec change the team owns.
- **Status:** Fixed
- **Fix applied:** TRD §18: `outillage Node : typescript, @types/node, reflect-metadata (décorateurs de fabric-contract-api), jest, eslint`. TRD v2.0.4, Plan v2.1.4, suite v2.1.4 in every header, `schema.sql`, AGENTS.md, PROGRESS.md; CHANGELOG entry `Suite v2.1.4` (marked: à confirmer par B). Applied by `audit/tools/apply_trd_deps_fix.py` (all-or-nothing, CRLF kept); exact-match check of all 13 document headers and of the plan §1 table. `jest` and `eslint` were already named in TRD §16 and §17, so no runtime library is added.

### AUD-039 — Stale header comment in `compose.yaml`

- **Severity:** Low
- **Category:** Docs
- **Location:** `fabric/compose/compose.yaml:4`
- **Description:** "Chaincode is a later increment: the Docker socket is intentionally not mounted." The file now defines the chaincode services. The second half is still true and is the reason for CCAAS.
- **Recommended fix:** reword: chaincode runs as external services (CCAAS) under the `spike` profile; the Docker socket stays unmounted.
- **Status:** Fixed
- **Fix applied:** Header comment of `compose.yaml` rewritten.

### AUD-047 — `test_check_ports_reports_a_busy_port` fails on WSL2 (kernel-assigned ports refuse connections)

- **Severity:** Info
- **Category:** Test
- **Location:** `tests/scripts/test_network_helpers.py::test_check_ports_reports_a_busy_port`
- **Description:** on the WSL2 distro used for the Linux run, a socket bound with `bind(("127.0.0.1", 0))` and `listen()` refuses connections from the same host (`connect_ex` → 111), while a socket bound to a fixed port accepts them (probe: 20001 … 60001 → 0). The test uses a kernel-assigned port, so the probe in `network.sh` sees the port as free and the test fails.
- **Evidence:** deterministic (6 of 6 runs); a minimal Python script reproduces it without the project. A native Linux kernel does not behave this way.
- **Root cause:** environment (WSL2 kernel 6.6.87.2 with `localhostForwarding=true`), not the project. The test and `network.sh` are correct.
- **Impact:** none on Windows or native Linux. The nested `test_board_flag_…` test fails on WSL2 only when pytest is run without `scripts/test-l.sh`, because it re-runs the local suite.
- **Recommended fix:** none. Re-check on a native Linux host or in CI.
- **Status:** Could not verify

### AUD-040 — Empty stray directory `fabric/builders/ccaas/bin/`

- **Severity:** Info
- **Category:** Architecture
- **Location:** `fabric/builders/ccaas/bin/`
- **Description:** an empty, untracked directory left from an abandoned approach (a local external builder). The peers use the builder shipped in the image (`/opt/hyperledger/ccaas_builder`, checked by `peers_have_builder`), so nothing references it.
- **Recommended fix:** remove the empty directory.
- **Status:** Fixed
- **Fix applied:** Empty directory `fabric/builders/` removed (untracked, no file, no reference).

### AUD-041 — File ownership and modes of generated wallet files on Linux

- **Severity:** Info
- **Category:** Config
- **Location:** `fabric/scripts/enroll-identities.sh:98-100`
- **Description:** wallet files are written by the container (root) and set to 0600, including the public `cert.pem`. On Linux Docker Engine, the host user could not read them, which `test_identities.py` (reads `cert.pem`) and the host `npm run spike:submit` need. On Docker Desktop (Windows/macOS) ownership is mapped, as observed here.
- **Evidence:** none obtainable: this host is Windows.
- **Recommended fix:** none without a Linux host. If it reproduces on the second workstation, make `cert.pem` 0644 and run the enrollment container as the host user.
- **Status:** Fixed
- **Fix applied:** Reproduced on real Linux (see AUD-046) and fixed there: wallet files and TLS CA certificate readable by the host user, build outputs owned by the checkout owner, cleanup possible. The Linux run used WSL2 Ubuntu 22.04 (ext4, uid 1000) against Docker Desktop's engine, which is not a native Docker Engine but does keep real ownership on those bind mounts (root-owned files appeared). Remaining uncertainty: rootless Docker or user-namespace remapping, not tried.

### AUD-042 — Demo chaincode authorizes on the `role` attribute only

- **Severity:** Info
- **Category:** Security
- **Location:** `chaincode/provenance/src/identity-spike.ts:16-20`
- **Description:** `Write` accepts any identity whose certificate carries `role=pipeline-agent`, whatever its MSP. The TRD (§8.3) specifies the same attribute check, and Org2's CA could mint such a certificate for an Org2 identity; the record keeps the MSP id so it is visible. A defence-in-depth check of `Org1MSP` is a decision for l04, where this demo is replaced.
- **Status:** Won't fix
- **Note:** Spike replaced in l04; noted for the l04 review.

### AUD-043 — `test_identities.py` source test is substring-based; the access rule has no unit test

- **Severity:** Info
- **Category:** Test
- **Location:** `tests/fabric/test_identities.py:101-113`
- **Description:** the static test accepts `name in enroll or name.removeprefix("agent-") in enroll`, which a loop over short names satisfies trivially; the chaincode rule is covered only by the (slow) Fabric test, and `npm test` is a type-check. Jest tests arrive with l04 per the plan; the behavioural test is the real guard here.
- **Status:** Won't fix
- **Note:** l04 adds Jest tests for the access rule; the Fabric test covers the behaviour today.

## 5. Fix plan (as executed)

1. Trivial first: AUD-036 (formatting), AUD-039 (comment), AUD-040 (empty directory).
2. Compose and scripts: AUD-028 (labels), AUD-035 (image pins), AUD-033 (mounts), AUD-029 (idempotent enrollment), AUD-031 (ledger-state deployment), AUD-034 (build flags), AUD-027 (modes).
3. Dependencies: AUD-030 (aligned packages, regenerated locks, `npm audit`).
4. Host path: AUD-032, AUD-044 (Node on the host).
5. Follow-up requested by the user: AUD-037 (TypeScript check never silently skipped), AUD-038 (TRD §18, suite v2.1.4), AUD-041 (Linux).
6. AUD-041 could only be settled by running on real Linux; that run found AUD-045, AUD-046, AUD-047. AUD-046 and AUD-045 were fixed and the suite re-run on both hosts.

No finding needs a user decision any more; AUD-038 is marked "à confirmer par B" in the CHANGELOG.

## 6. Verification (after changes)

| Check | Before (baseline) | After |
|---|---|---|
| Local suite, Windows (`bash scripts/test-l.sh`) | 19 passed, 1 skipped | **51 passed, 1 skipped** (+32 tests); both Node packages type-check (`tsc --noEmit`) |
| Fabric suite, Windows (`bash scripts/test-l.sh --fabric`) | 4 passed, 617 s | **8 passed, 538 s**, exit 0. Includes the second enrollment, the stop-with-leftover-container test, 3 start/stop cycles and the Docker-fallback TypeScript checks |
| Fabric suite, **real Linux** (WSL2 Ubuntu 22.04, ext4, uid 1000, Docker Desktop engine; `audit/tools/linux_check.sh`) | not run before this audit; first run: **5 failed, 1 error** (AUD-046) | **8 passed**, 233 s; no root-owned file left in the checkout |
| Local suite, Linux | `./scripts/test-l.sh`: "pytest is not available" (AUD-045) | 50 passed; 1 failure, `test_check_ports_reports_a_busy_port`, caused by the WSL2 kernel (AUD-047), plus the nested `test_board_flag_…` which re-runs it when pytest is started directly |
| Node fallback on Linux (no Node on the host) | not tested | `run_npm_test` runs both packages in the pinned Node image; passes |
| `ruff check .` | pass | pass |
| `ruff format --check .` | **fail (2 files)** | pass (40 files) |
| `mypy tests` | pass (7 files) | pass (9 files) |
| `bash -n` on every script | pass | pass |
| `docker compose … config -q` | exit 0 | exit 0 |
| `npm audit` (host Node 22) | 2 lockfiles with high-severity advisories (registry API) | **found 0 vulnerabilities** in both packages |
| Residue after the suites | none | none: 0 containers, 0 labeled volumes, no network, no `fabric/wallet` (both hosts) |

Red/green evidence: stop with a leftover build container (red without the label, green with it); Linux Fabric suite (red before AUD-046, green after); mode test (flagged `audit/tools/verify_schema_patch.sh`); negative control for the TypeScript check (an injected type error gives `error TS2322` and a non-zero exit, in the host and the container path).

No test was deleted, skipped or weakened. Test counts: 24 in the baseline, 60 now (51 passed and 1 skipped locally, 8 Fabric).

Regressions: none. Open on Linux: AUD-047 (environment).

## 7. Re-audit

Files re-inspected after the fixes: 24 (everything in section 4 of `audit/round-2/INVENTORY.md` plus `compose.yaml`, `fabric/network.sh`, `fabric/scripts/enroll-identities.sh`, `scripts/test-l.sh`, the six new or changed tests, `audit/tools/linux_check.sh`). New findings from the re-audit: AUD-045, AUD-046 (both from the Linux run) — fixed and re-run on both hosts. Observations, no action: the `umask 077` set in `write_identity_secrets` leaks into later steps of that shell (harmless: later files are runtime state); two near-identical Python lookups (`network.sh`, `enroll-identities.sh`, `test-l.sh`) — a shared library is premature; `CHAINCODE_ID` env in `cc-org*` is redundant with `--chaincode-id`.

## 8. Unresolved

| ID | Severity | Status | Reason | Risk if left | What is needed |
|---|---|---|---|---|---|
| AUD-047 | Info | Could not verify | WSL2 kernel refuses connections to kernel-assigned loopback ports; native Linux not available | None for the project; one test is red on WSL2 | Run `tests/scripts` on a native Linux host or CI |
| AUD-042 | Info | Won't fix | Demo chaincode is replaced in l04 | Role attribute checked without the MSP | l04 review: add an `Org1MSP` check if wanted |
| AUD-043 | Info | Won't fix | Jest tests arrive with l04 | Access rule covered only by the slow Fabric test | l04 |
| (git) | n/a | Action needed | Fixes are uncommitted next to the T1.4 work; modes of 6 tracked scripts are staged (mode only) | The four new scripts would be committed as `100644` and fail the new mode test | `git add --chmod=+x fabric/enroll-identities.sh fabric/spike-submit.sh fabric/scripts/enroll-identities.sh fabric/scripts/deploy-identity-spike.sh` when staging T1.4 |
| (platform) | n/a | Not covered | The Linux run used Docker Desktop's engine through WSL2, not a native Docker Engine; rootless Docker and user-namespace remapping were not tried | Ownership behaviour could differ there | The second-workstation test (A-02.3) |

Round-1 items still open (AUD-001, AUD-021: `pyproject.toml`, CI, `.env.example`, README) are unchanged.
