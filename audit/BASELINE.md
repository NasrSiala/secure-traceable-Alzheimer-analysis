# Baseline — before any change

Date: 2026-11-09 · Host: Windows 11, Git Bash, Docker Desktop 29.9.2 (Linux engine, Compose v5.6.1), Python 3.14.7 (`py -3`, pytest 9.1.1, ruff 0.17.4, mypy 2.4.1), Python 3.10.14 (`python`, `uv`), no Node.js, no shellcheck, no psql, no gh.

| Check | Command | Result | Pre-existing? |
|---|---|---|---|
| Install | `uv sync` | **Not runnable**: no `pyproject.toml`, `uv.lock` or `package.json` anywhere (T1.1 not done) | pre-existing, tracked in PROGRESS.md |
| Tests, local suite | `py -3 -m pytest -q -o addopts= -m "not fabric and not board" tests` | **12 passed**, 2 deselected, 15.2 s | — |
| Tests, project entry point | `bash scripts/test-l.sh` | **12 passed**, exit 0, 6.9 s | — |
| Tests, documented command | `uv run pytest -q` (AGENTS.md) | **FAIL**: `ModuleNotFoundError: No module named 'pytest'` (uv resolved Python 3.10's global `pytest.exe`; no project environment exists) | pre-existing → AUD-001 |
| Tests, Fabric lifecycle | `py -3 -m pytest -q -o addopts= -m fabric tests` | **2 passed** in 264 s (3 start/stop cycles; network healthy each time; no residue; foreign containers/volumes/networks preserved) | — |
| Shell syntax | `bash -n` on 5 scripts | all OK | — |
| YAML | `yaml.safe_load` on `configtx.yaml`, `compose.yaml`; `docker compose config -q` | all OK | — |
| Lint | `py -3 -m ruff check .` (no config in repo) | **3 errors** (ISC004 `tests/fabric/test_network.py:113`; PIE810 ×2 `tests/scripts/test_git_hygiene.py:27`) | pre-existing → AUD-010 |
| Format | `py -3 -m ruff format --check .` | **3 files would be reformatted** (`test_network.py`, `test_git_hygiene.py`, `test_network_contract.py`) | pre-existing → AUD-010 |
| Type check | `py -3 -m mypy tests` | OK, no issues in 5 files (non-strict; no `saam/` package exists yet) | — |
| `mypy saam`, `lint-imports`, `tests/arch` | AGENTS.md commands | Not runnable: no `saam/` package, no import-linter contracts | pre-existing → AUD-001 |
| Build | — | No buildable artefact exists (no frontend, gateway, chaincode, image) | n/a |
| Dependency scan | `pip-audit` / `npm audit` | **Not applicable**: no dependency manifests. Container images are pinned by tag only (AUD-025) | n/a |
| App start | `fabric/network.sh start` | OK via the lifecycle test above (healthy: 3 CAs, orderer, 2 peers, channel `medtrace`, LevelDB) | — |
| Spec DDL | `psql -f schema.sql` in throw-away `postgres:16-alpine` | **0 errors, 13 tables** | — |
| Spec cross-checks | link check, ID census, version headers, arithmetic | 1 false positive (`%20` link), IDs consistent, 2 stale version cells (AUD-012) | — |
| Could not run | shellcheck, Node/Jest (no JS code yet), Vivado/GHDL/cocotb (no HDL yet), board tests | recorded under "Could not verify" in the report | — |

Working-tree note: at audit start `main` had 16 modified spec/agent files and all of `fabric/`, `scripts/`, `tests/`, `pytest.ini`, `.gitattributes`, `08-implementation-plan-L.md` untracked (the uncommitted T1.3 increment).
