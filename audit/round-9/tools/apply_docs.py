"""Round-9 edits to PROGRESS.md and hw/BRINGUP.md (French, like the files). Every anchor must occur
once. Run once on the tree as it is after the code fixes."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def edit(relative: str, pairs: list[tuple[str, str]]) -> None:
    path = ROOT / relative
    raw = path.read_bytes()
    assert b"\r\n" not in raw, f"{relative} has CRLF"
    text = raw.decode("utf-8")
    for old, new in pairs:
        if text.count(old) != 1:
            sys.exit(f"{relative}: anchor found {text.count(old)} times: {old[:70]!r}")
        text = text.replace(old, new)
    path.write_bytes(text.encode("utf-8"))
    print("edited", relative)


# --- hw/BRINGUP.md ------------------------------------------------------------------------------
edit(
    "hw/BRINGUP.md",
    [
        (
            "Les mesures de débit sont écrites dans `hw/reports/bringup-uart.json` par une exécution réelle.\n",
            (
                "Les mesures de débit sont écrites dans `hw/reports/bringup-uart.json` par une exécution réelle.\n"
                "\n"
                "Sans carte, la console est aussi exercée sur le PC : `hw/host/tests/test_hello_console.py` compile\n"
                "`hello.c` tel quel avec un compilateur C de l'hôte (`gcc` ou `cc` ; sans lui, les tests sont\n"
                "ignorés avec la raison), des en-têtes factices (`hw/host/tests/hello_stub/`) et un UART sur des\n"
                "tubes, puis la fait parler à `bringup_support.Console`. Cela vérifie l'analyse des commandes, les\n"
                "limites, les réponses, l'ordre des appels au matériel et l'accord entre les deux côtés ; cela ne\n"
                "prouve rien sur l'UART, le PL ni la carte.\n"
            ),
        )
    ],
)

# --- PROGRESS.md ----------------------------------------------------------------------------------
progress = ROOT / "PROGRESS.md"
lines = progress.read_bytes().decode("utf-8").split("\n")

row = next(
    i
    for i, line in enumerate(lines)
    if line.startswith("| T1.9 `l10-board-bringup` (partiel, sans carte) |")
)
assert lines[row].endswith(" |")
lines[row] = (
    lines[row][:-2]
    + " Après l'audit du 2026-11-16 (passe 9) : `scripts/test-l.sh` 454 passed et 3 skipped (Jest 183 et 212) ; "
    "`hw/host/tests` 83 passed hors carte, dont 52 de `test_hello_console.py` (`hello.c` compilé tel quel sur l'hôte avec des en-têtes factices, "
    "puis piloté par `bringup_support.Console` : l'accord des deux côtés est vérifié, pas la carte) ; "
    "`axil_reg_bringup.vhd` simulé dans xsim avec un banc de protocole AXI4-Lite (`audit/round-9/tools/xsim/`) : propre, 12 mutations sur 12 détectées ; "
    "`hello.c` compilé avec les vrais pilotes de Vitis 2025.2 (`XILINX_VITIS` : 25 passed pour `test_bringup_config.py`) ; Linux (WSL2) : 130 passed ; "
    "`SAAM_ZYBO_PORT=COM99 scripts/test-l.sh --board` : phase locale verte, puis « no board test passed » et sortie 4 (`pyserial` absent). "
    "Toujours aucun résultat de carte. |"
)

problems = next(
    i
    for i, line in enumerate(lines)
    if line.startswith("| 2026-11-16 | Audit de code, passe 8")
)
lines.insert(
    problems + 1,
    "| 2026-11-16 | Audit de code, passe 9 (`audit/round-9/AUDIT_REPORT.md`) : 7 constats sur l'arbre de l10, aucun critique ni majeur, deux moyens. "
    "Corrigés : la commande documentée `SAAM_ZYBO_PORT=COM5 scripts/test-l.sh --board` échouait, car la phase locale héritait du port et un test de la suite appelait `--board` (il ouvrait la carte) ; "
    "`--board` annonçait « board-access: tests-only » quand tous les tests de carte étaient ignorés (maintenant `-rs` et sortie 4) ; "
    "`hello.c` changeait la vitesse de l'UART dès que le FIFO d'émission était vide, alors que `XUartPs_SetBaudRate` coupe l'UART et remet l'émetteur à zéro (lu dans le pilote 3.17) : "
    "le dernier caractère de l'accusé `B 921600` pouvait être coupé, il attend maintenant `XUartPs_IsTransmitActive` (à confirmer sur la carte) ; "
    "`hw/SAAM/` (124 fichiers générés, dont un `.sh`, 30 avec le nom de la machine) n'était pas ignoré par git ; une erreur mypy de `test_bringup_config.py` ; "
    "la console de `hello.c` n'était testée que par recherche de mots (10 mutations sur 12 passaient) ; deux phrases fausses. "
    "Reste : aucun constat ouvert, mais la définition de fini de T1.9 attend la carte. | T1.9 | corrigé ; carte à venir |",
)

nb = next(
    i
    for i, line in enumerate(lines)
    if line.startswith(
        "| 2026-11-16 | `hw/SAAM/` (projet Vivado de l'utilisateur) n'est pas ignoré par git"
    )
)
old = "n'est pas ignoré par git : ne pas le commiter ; ajouter une règle `.gitignore` quand le nom du projet est fixé."
new = (
    "est ignoré par git (règles `hw/**/*.xpr`, `*.cache/`, `*.runs/`, `*.hw/`, `*.ip_user_files/`, `*.sim/`, `*.gen/`, `*.srcs/`, "
    "quel que soit le nom du projet : audit passe 9) ; ne pas le commiter quand même."
)
assert lines[nb].count(old) == 1
lines[nb] = lines[nb].replace(old, new)

progress.write_bytes("\n".join(lines).encode("utf-8"))
print("edited PROGRESS.md")
