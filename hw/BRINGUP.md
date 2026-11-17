# Mise en route de la Zybo Z7-10 (T1.9, `l10-board-bringup`)

Spike : prouver que la carte démarre depuis la carte SD, que le PS écrit et relit un registre du PL
en AXI4-Lite, et mesurer le débit de l'UART à 115 200 et à 921 600 bauds. Ce n'est pas le design du
projet : les cœurs SHA-256 et FIR (T3.20, T3.21) et l'application finale (T4.12) viennent plus tard.

## Ce qui est prouvé, et ce qui ne l'est pas

Les résultats du spike sont consignés dans [PROGRESS.md](../PROGRESS.md) **uniquement** quand ils
viennent d'une exécution réelle. Les tests de `tests/scripts/test_bringup_config.py` et de
`hw/host/tests/test_bringup_support.py` ne prouvent rien sur la carte : ils vérifient les scripts
avec un interpréteur Tcl factice, la source C contre les en-têtes réels des pilotes Xilinx, et le
code côté PC avec un port série factice. Un test `board` ignoré (« skipped ») n'est pas un test réussi.

## Prérequis

| Élément | État attendu |
|---|---|
| Vivado et Vitis | 2023.1 ou plus récent (D-12) ; installés en 2025.2 (Vivado, Vitis Unifié, `bootgen`, GCC ARM bare-metal) |
| Fichiers de carte Digilent `zybo-z7-10` | installés dans Vivado (Q-14 : licence de ces fichiers à consigner) ; sans eux le PS7 n'a pas de préréglage DDR/MIO |
| Projet Vivado | créé **à la main avec la carte Zybo Z7-10** (partie `xc7z010clg400-1`, `BOARD_PART` `digilent.com:zybo-z7-10:*`) |
| Carte | alimentée par l'USB, JP5 sur **SD** pour la démo, câble micro-USB (JTAG + UART) |
| PC | `pyserial` (TRD §18) pour les tests de carte |

`build.tcl` refuse un projet sans la carte ou pour une autre partie : un PS7 sans le préréglage de
la carte ne démarre pas sur le matériel.

## Construire

```bash
# 1. Design Vivado : PS7 + un registre AXI4-Lite à 0x43C00000, bitstream, XSA, rapports.
SAAM_VIVADO_PROJECT=chemin/vers/projet.xpr \
  vivado -mode batch -source hw/vivado/build.tcl

# 2. Application Vitis (FSBL + hello) et BOOT.bin à partir du XSA (Vitis Unifié).
vitis -s hw/ps_app/bringup/build_app.py
```

Produits (ignorés par git) : `hw/build/bringup/bringup.xsa`, `hw/build/bringup/boot/BOOT.bin`.
Rapports versionnés : `hw/reports/bringup-utilization.rpt`, `bringup-timing.rpt` et
`bringup-environment.json` (version de Vivado, partie, carte : la réponse à Q-14, avec
`Help › Manage License` pour l'édition).

## Carte SD

FAT32, `BOOT.bin` à la racine, rien d'autre n'est nécessaire. Mettre JP5 sur SD, brancher, la LED
« DONE » s'allume quand le bitstream est chargé.

## Tester

Le port série de l'UART est le **second** port du FT2232 de la carte (le premier est le JTAG).

```bash
SAAM_ZYBO_PORT=COM5 scripts/test-l.sh --board          # ou /dev/ttyUSB1
SAAM_ZYBO_PORT=COM5 py -3 -m pytest -m board hw/host/tests -o addopts= -rs
```

Sans `SAAM_ZYBO_PORT`, les tests de carte sont ignorés avec la raison et aucun port n'est ouvert.
Les mesures de débit sont écrites dans `hw/reports/bringup-uart.json` par une exécution réelle.

Sans carte, la console est aussi exercée sur le PC : `hw/host/tests/test_hello_console.py` compile
`hello.c` tel quel avec un compilateur C de l'hôte (`gcc` ou `cc` ; sans lui, les tests sont
ignorés avec la raison), des en-têtes factices (`hw/host/tests/hello_stub/`) et un UART sur des
tubes, puis la fait parler à `bringup_support.Console`. Cela vérifie l'analyse des commandes, les
limites, les réponses, l'ordre des appels au matériel et l'accord entre les deux côtés ; cela ne
prouve rien sur l'UART, le PL ni la carte.

## Console du spike (`hw/ps_app/bringup/hello.c`)

Lignes de texte, une requête par ligne (LF), réponse terminée par CR LF. Ce n'est pas le protocole
trame d'IF-14.

| Requête | Réponse |
|---|---|
| `H` | `hello SAAM-BRINGUP 1` |
| `W <hex>` | `OK` (écrit le registre) |
| `R` | `R <8 chiffres hex>` |
| `B 115200` ou `B 921600` | `B <baud>` au débit actuel, puis changement de débit |
| `E <n>` (n ≤ 65 536) | `GO`, puis écho des n octets suivants, puis une ligne vide et `DONE` |

## Versions des outils, et ce qui a été vérifié

- **Vitis 2025.2 : flot Unifié seulement.** `xsct` existe encore mais son `app create` demande le
  service Eclipse que 2025.2 n'installe plus (pas de dossier `eclipse`) : `build_app.py`
  (`vitis -s`) remplace le script Tcl. Pour Vitis 2023.x, le flot `xsct` serait à réécrire.
- **Pilote UART :** deux formes dans Vitis 2025.2, par numéro de périphérique et avec SDT (par
  adresse de base). `hello.c` compile avec les deux (`-DSDT`) : vérifié avec le GCC ARM contre les
  en-têtes réels du pilote.
- **Module de référence :** Vivado 2025.2 refuse un module dont le fichier du haut est typé
  VHDL-2008 (`filemgmt 56-195`) ; le registre est ajouté en VHDL standard. Les enveloppes AXI de
  T3.20 devront en tenir compte.
- **Vérifié avec les vrais outils sur un projet de test sans carte** (partie seule, pas de
  préréglage de carte) : les commandes du block design de `build.tcl` (PS7, registre en module de
  référence, automatisation AXI, adresse `0x43C00000`, FCLK0 100 MHz) produisent un XSA ; `xsct`
  génère la plateforme et le FSBL. **Non vérifié :** `build_app.py` n'a pas pu s'exécuter ici
  (`vitis.create_client()` échoue sur un décodage UTF-8 de la sortie du serveur Vitis, poste en
  français) ; le build complet avec la carte (préréglage PS, implémentation, bitstream), le
  démarrage SD, le registre depuis le PS et le débit UART restent à faire sur le poste avec la carte.
