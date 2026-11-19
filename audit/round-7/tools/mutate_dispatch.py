"""Audit helper: the structural test of the shared dispatch must go red for each mutation."""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
COPY = [
    "tests/conftest.py",
    "tests/scripts/test_history_check_script.py",
    "tests/scripts/gateway_run_support.py",
    "fabric/lib/gateway-run.sh",
    "fabric/gateway-check.sh",
    "fabric/history-check.sh",
    "fabric/model-check.sh",
    "fabric/gateway-routes-check.sh",
    "fabric/spike-latency.sh",
]


def run(root: Path) -> str:
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/scripts/test_history_check_script.py",
            "-k",
            "share_one_dispatch",
            "-q",
            "-o",
            "addopts=",
            "-p",
            "no:cacheprovider",
        ],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    return (
        ("green" if r.returncode == 0 else "RED")
        + " | "
        + r.stdout.strip().splitlines()[-1]
    )


def fresh() -> Path:
    base = Path(tempfile.mkdtemp())
    for name in COPY:
        (base / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / name, base / name)
    return base


def edit(path: Path, old: str, new: str) -> None:
    text = path.read_bytes().decode("utf-8")
    assert old in text, (path, old)
    path.write_bytes(text.replace(old, new, 1).encode("utf-8"))


cases = {
    "unmutated": lambda b: None,
    "header without gateway-routes-check.sh": lambda b: edit(
        b / "fabric/lib/gateway-run.sh",
        "fabric/gateway-routes-check.sh",
        "fabric/the-routes-script.sh",
    ),
    "host_can_run() copied into gateway-routes-check.sh": lambda b: edit(
        b / "fabric/gateway-routes-check.sh",
        "main() {",
        "host_can_run() { true; }\nmain() {",
    ),
    "new fabric/other-check.sh with its own dispatch": lambda b: (
        b / "fabric/other-check.sh"
    ).write_text("#!/usr/bin/env bash\nhost_can_run() { true; }\n", encoding="utf-8"),
    "new fabric/other-check.sh sourcing the library but not named in it": lambda b: (
        b / "fabric/other-check.sh"
    ).write_text(
        '#!/usr/bin/env bash\nsource "${FABRIC_DIR}/lib/gateway-run.sh"\n',
        encoding="utf-8",
    ),
}
for label, mutate in cases.items():
    base = fresh()
    mutate(base)
    print(f"{label:70s} {run(base)}")
    shutil.rmtree(base, ignore_errors=True)
