"""Static checks on the Node packages and on the scripts that build and deploy them.

They need neither Node nor Docker: they read package.json, package-lock.json and the
sources. AUD-030, AUD-031, AUD-032, AUD-034 (audit round 2).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

PACKAGES = ("chaincode/provenance", "ledger-gateway")
SINGLE_COPY = (
    "fabric-contract-api",
    "fabric-shim",
    "fabric-shim-api",
    "reflect-metadata",
    "@grpc/grpc-js",
)


def _json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _copies(lock: dict[str, object], name: str) -> list[str]:
    """Versions of `name` installed anywhere in the lockfile's tree."""
    packages = lock["packages"]
    assert isinstance(packages, dict)
    return [
        str(entry["version"])
        for path, entry in packages.items()
        if path.endswith(f"node_modules/{name}")
    ]


@pytest.mark.parametrize("package", PACKAGES)
def test_node_dependencies_are_exact_pins(repo_root: Path, package: str) -> None:
    manifest = _json(repo_root / package / "package.json")
    for section in ("dependencies", "devDependencies"):
        declared = manifest.get(section, {})
        assert isinstance(declared, dict)
        for name, spec in declared.items():
            assert re.fullmatch(r"\d+\.\d+\.\d+", str(spec)), (
                f"{package}: {name} {spec}"
            )


@pytest.mark.parametrize("package", PACKAGES)
def test_lockfile_matches_package_json(repo_root: Path, package: str) -> None:
    """`npm ci` fails on a mismatch; so must this test, before anyone runs Docker."""
    manifest = _json(repo_root / package / "package.json")
    lock = _json(repo_root / package / "package-lock.json")
    packages = lock["packages"]
    assert isinstance(packages, dict)
    root = packages[""]
    for section in ("dependencies", "devDependencies"):
        assert root.get(section, {}) == manifest.get(section, {}), (
            f"{package}: {section}"
        )


@pytest.mark.parametrize("package", PACKAGES)
def test_npm_scripts_run_typescript_through_node(repo_root: Path, package: str) -> None:
    """AUD-044: node_modules built in a Linux container holds `.bin` symlinks that a
    Windows npm cannot run ("'tsc' is not recognized"); calling the compiler through
    `node` works for modules installed on either side of the bind mount."""
    manifest = _json(repo_root / package / "package.json")
    scripts = manifest["scripts"]
    assert isinstance(scripts, dict)
    for name in ("build", "test"):
        assert str(scripts[name]).startswith("node node_modules/typescript/bin/tsc"), (
            name
        )


def test_shim_and_contract_api_are_one_release_with_one_copy(repo_root: Path) -> None:
    """AUD-030: fabric-shim pins its own fabric-contract-api; mixed releases give two copies."""
    manifest = _json(repo_root / "chaincode/provenance" / "package.json")
    dependencies = manifest["dependencies"]
    assert isinstance(dependencies, dict)
    assert dependencies["fabric-shim"] == dependencies["fabric-contract-api"]
    lock = _json(repo_root / "chaincode/provenance" / "package-lock.json")
    for name in SINGLE_COPY:
        assert len(_copies(lock, name)) == 1, f"{name}: {_copies(lock, name)}"
    assert _copies(lock, "fabric-shim") == [dependencies["fabric-shim"]]


@pytest.mark.parametrize("package", PACKAGES)
def test_grpc_js_is_past_the_known_advisories(repo_root: Path, package: str) -> None:
    """AUD-030: GHSA-5375-pq7m-f5r2, GHSA-99f4-grh7-6pcq, GHSA-m9gg-hp2v-232j (fixed in 1.13.6)."""
    lock = _json(repo_root / package / "package-lock.json")
    versions = _copies(lock, "@grpc/grpc-js")
    assert versions
    for version in versions:
        assert tuple(int(part) for part in version.split(".")[:3]) >= (1, 13, 6), (
            version
        )


@pytest.mark.parametrize("package", PACKAGES)
def test_deepmerge_stays_outside_the_unpatched_advisory(
    repo_root: Path, package: str
) -> None:
    """AUD-063, AUD-075 (workaround): GHSA-gcqx-w48m-w2h4 covers deepmerge >= 4.2.0, <= 4.3.1
    and no release is patched. Only jest-config uses it (merging `globals` of a preset, which
    these packages' jest.config.js do not have), so the override pins 4.1.2, the last release
    before the range, and `npm audit` stays at 0. Remove the override, and this test, when
    deepmerge publishes a fix or Jest stops using it."""
    package_dir = repo_root / package
    manifest = _json(package_dir / "package.json")
    assert manifest["overrides"] == {"deepmerge": "4.1.2"}
    lock = _json(package_dir / "package-lock.json")
    assert _copies(lock, "deepmerge") == ["4.1.2"]


@pytest.mark.parametrize("package", PACKAGES)
def test_npm_test_removes_stale_compiled_tests_first(
    repo_root: Path, package: str
) -> None:
    """AUD-061, AUD-076: Jest runs dist-test/**/*.test.js. A file compiled from a test that was
    renamed or deleted would keep running, so `npm test` empties dist-test before compiling."""
    manifest = _json(repo_root / package / "package.json")
    scripts = manifest["scripts"]
    assert isinstance(scripts, dict)
    test = str(scripts["test"])
    assert "rmSync('dist-test'" in test
    assert test.index("rmSync('dist-test'") < test.index("-p tsconfig.test.json")
    assert (repo_root / package / "tsconfig.test.json").is_file()
    ignored = (repo_root / ".gitignore").read_text(encoding="utf-8")
    assert f"{package}/dist-test/" in ignored


def test_the_gateway_declares_the_node_it_needs(repo_root: Path) -> None:
    """AUD-080: fastify -> light-my-request -> cookie@2 is an ES module, loaded from this
    CommonJS package through require(esm), which Node has without a flag from 20.19. Older
    runtimes fail at `require("fastify")` with ERR_REQUIRE_ESM, far from the cause."""
    manifest = _json(repo_root / "ledger-gateway" / "package.json")
    assert manifest["engines"] == {"node": ">=20.19.0"}
    lock = _json(repo_root / "ledger-gateway" / "package-lock.json")
    packages = lock["packages"]
    assert isinstance(packages, dict)
    assert packages[""]["engines"] == {"node": ">=20.19.0"}


def test_no_setting_is_read_with_a_nullish_default(repo_root: Path) -> None:
    """AUD-073: `process.env.X ?? default` keeps an empty string, which `env_file:` and
    `--env-file` produce for every key of .env.example. Settings go through `envSetting`."""
    offenders = []
    for source in sorted((repo_root / "ledger-gateway" / "src").glob("*.ts")):
        for number, line in enumerate(
            source.read_text(encoding="utf-8").splitlines(), 1
        ):
            code = line.split("//")[0]
            if re.search(r"process\.env(\.\w+|\[[^\]]+\])\s*\?\?", code):
                offenders.append(f"{source.name}:{number}")
    assert offenders == []


def test_env_example_leaves_only_the_required_key_empty(repo_root: Path) -> None:
    """AUD-073: an optional key that ships as `NAME=` is set to "" by anyone who copies the file."""
    lines = (
        (repo_root / "ledger-gateway" / ".env.example")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    empty = [
        line.split("=")[0] for line in lines if re.fullmatch(r"[A-Z_]+=", line.strip())
    ]
    assert empty == ["AGENT_TOKEN_FILE"]


def test_build_uses_the_lockfile_and_skips_install_scripts(repo_root: Path) -> None:
    """AUD-034."""
    script = (repo_root / "fabric" / "enroll-identities.sh").read_text(encoding="utf-8")
    assert "npm ci --ignore-scripts" in script
    assert "--package-lock-only" not in script


def test_host_script_calls_the_network_script_through_bash(repo_root: Path) -> None:
    """AUD-027: no dependence on the executable bit of a sibling script."""
    script = (repo_root / "fabric" / "enroll-identities.sh").read_text(encoding="utf-8")
    assert re.search(
        r"^\s*bash \./network\.sh (stop|start|status)", script, re.MULTILINE
    )
    assert not re.search(r"^\s*\./network\.sh", script, re.MULTILINE)


def test_chaincode_packages_are_reproducible_archives(repo_root: Path) -> None:
    """AUD-029/031: the same inputs must give the same package identifier on a re-run."""
    script = (repo_root / "fabric" / "enroll-identities.sh").read_text(encoding="utf-8")
    assert "mtime=0" in script
    assert 'mode="w:gz"' not in script


def test_deploy_script_checks_the_ledger_not_the_error_text(repo_root: Path) -> None:
    """AUD-031: a failed commit is never excused by what its message happens to contain."""
    script = (repo_root / "fabric" / "scripts" / "deploy-chaincode.sh").read_text(
        encoding="utf-8"
    )
    host = (repo_root / "fabric" / "deploy-chaincode.sh").read_text(encoding="utf-8")
    assert "/work/scripts/deploy-chaincode.sh" in host
    assert "querycommitted" in script
    assert 'grep -q "identity-spike"' not in script
    assert 'grep -q "provenance"' not in script
    assert "calculatepackageid" in script


def test_spike_submit_defaults_work_from_a_host_with_node(repo_root: Path) -> None:
    """AUD-032: the process that dials the peer uses a certificate name and the wallet TLS CA."""
    source = (repo_root / "ledger-gateway" / "src" / "fabric-client.ts").read_text(
        encoding="utf-8"
    )
    code = "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith("//")
    )
    assert 'envSetting("PEER_ENDPOINT", "localhost:18051")' in code
    assert "127.0.0.1" not in code  # not one of the names in the peer's TLS certificate
    assert 'process.env.PEER_TLS_CERT ?? ""' not in code
    assert (
        "peer0-org1-tls-ca.crt" in code
    )  # from the wallet: organizations/ is root-only on Linux
    assert "organizations" not in code
    spike = (repo_root / "ledger-gateway" / "src" / "spike-submit.ts").read_text(
        encoding="utf-8"
    )
    assert "X-Agent-Token" in spike
    assert "/ledger/artifacts" in spike


def test_gateway_check_reaches_the_spike_service(repo_root: Path) -> None:
    script = (repo_root / "fabric" / "gateway-check.sh").read_text(encoding="utf-8")
    assert "GATEWAY_SCENARIO" in script
    assert "check:gateway" in script
    assert "organizations" not in script
