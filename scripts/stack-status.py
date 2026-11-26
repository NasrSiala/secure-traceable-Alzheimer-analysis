"""Consigner la santé et la mémoire de la pile T1.5 et du réseau Fabric."""

from __future__ import annotations

import argparse
import json
import re
import ssl
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def docker(*args: str) -> str:
    result = subprocess.run(
        ["docker", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return result.stdout


def memory_mib(text: str) -> float:
    matched = re.fullmatch(r"\s*([\d.]+)\s*(B|KiB|MiB|GiB|kB|MB|GB)\s*", text)
    if matched is None:
        raise ValueError("Unité mémoire Docker inconnue")
    factors = {
        "B": 1,
        "KiB": 1024,
        "MiB": 1024**2,
        "GiB": 1024**3,
        "kB": 1000,
        "MB": 1000**2,
        "GB": 1000**3,
    }
    return float(matched[1]) * factors[matched[2]] / 1024**2


def statistics(ids: list[str]) -> list[dict[str, Any]]:
    if not ids:
        return []
    records = []
    for line in docker(
        "stats", "--no-stream", "--format", "{{json .}}", *ids
    ).splitlines():
        item = json.loads(line)
        records.append(
            {
                "name": item["Name"],
                "memory_mib": memory_mib(item["MemUsage"].split("/")[0]),
                "cpu": item["CPUPerc"],
            }
        )
    return records


def report(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
    with urllib.request.urlopen(
        request, timeout=8, context=ssl._create_unverified_context()
    ) as response:
        health = json.load(response)
    if health.get("status") != "ok" or len(health.get("services", {})) != 5:
        raise ValueError("La pile doit avoir ses cinq services sains")
    stack_ids = docker(
        "ps", "-q", "--filter", "label=com.docker.compose.project=saam-stack"
    ).split()
    fabric_ids = docker("ps", "-q", "--filter", "label=saam.network=medtrace").split()
    stack = statistics(stack_ids)
    fabric = statistics(fabric_ids)
    return {
        "date": datetime.now(UTC).isoformat(),
        "health": health,
        "scope": "Socle T1.5 : API, worker sans graphe ni modèle chargé, PostgreSQL, passerelle, nginx, Fabric",
        "stack": stack,
        "fabric": fabric,
        "stack_memory_mib": round(sum(item["memory_mib"] for item in stack), 2),
        "fabric_memory_mib": round(sum(item["memory_mib"] for item in fabric), 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="https://localhost/api/v1/health")
    parser.add_argument(
        "--output", type=Path, default=ROOT / ".tools" / "t15-stack-status.json"
    )
    args = parser.parse_args()
    result = report(args.url)
    result["total_memory_mib"] = (
        result["stack_memory_mib"] + result["fabric_memory_mib"]
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        f"5 services sains ; pile {result['stack_memory_mib']:.2f} MiB ; "
        f"Fabric {result['fabric_memory_mib']:.2f} MiB ; total {result['total_memory_mib']:.2f} MiB"
    )


if __name__ == "__main__":
    main()
