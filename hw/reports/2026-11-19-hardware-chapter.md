# Chapitre matériel — contribution L (T6.2)

Date : 2026-11-19. Branche de travail : `l12-sha256-padder-multiblock` (étiquette seulement, aucune branche l13–l26 créée). Revue à deux membres : **non faite** (A-02.3, I et B non nommés). Ce texte ne remplace pas cette revue.

Les nombres ci-dessous sont des mesures de simulation xsim (Vivado 2025.2, build 6299465) ou des mesures déjà écrites dans `PROGRESS.md` pour un autre design. Aucun bitstream du design SHA-256 + FIR n'a été produit dans cette session. Aucun WNS, aucune utilisation LUT/FF/BRAM/DSP du design intégré, aucune durée de démarrage SD.

## Architecture

Deux cœurs dans `hw/rtl/`, chacun derrière un esclave AXI4-Lite, plus le protocole UART IF-14 côté hôte.

- `sha256_core.vhd` compresse des blocs déjà bourrés. `sha256_padder.vhd` applique le bourrage FIPS 180-4. `sha256_axi.vhd` expose IF-15 : `CTRL` 0x00, `STATUS` 0x04, `DATA_IN` 0x08, `LAST_BYTES` 0x0C, `DIGEST0`–`DIGEST7` 0x10–0x2C, `VERSION` 0x30. Le générique `VERSION` vaut `0` tant que T3.21 ne l'alimente pas avec le SHA git.
- `fir_decim.vhd` est un MAC séquentiel, ligne à retard de 111, décimation par 5, arrondi par addition de 2^14 puis décalage arithmétique de 15, saturation int16. Les coefficients viennent de `fir_coeffs_pkg.vhd`, généré, non édité. `fir_coef_id` = `ca0e824c`. `fir_axi.vhd` expose IF-16 : `CTRL`/`CLEAR` 0x00, `STATUS` 0x04, `DATA_IN` 0x08, `DATA_OUT` 0x0C (la lecture consomme), `COEF_ID` 0x10, `VERSION` 0x14.
- L'hôte (`hw/host/zybo_client.py`, `ps_model.py`) parle IF-14 : `0xA5`, commande, longueur petit-boutiste, charge, CRC-32 IEEE. Une tentative plus trois réessais, puis « Erreur de transmission ». Pas de réponse : « Carte injoignable — vérifiez le câble USB et le démarrage SD. »

## Mesures de simulation (cette session)

| Banc | Résultat | Horloge simulée | Preuve |
|---|---|---|---|
| `fir_decim_extremes_tb` | `FIR_DECIM_EXTREMES_TB PASSED` | 54 237 500 ps | `hw/reports/2026-11-19-xsim-l14-l16.log` |
| `sha256_axi_tb` | `sha axi vectors: 1018` puis `SHA256_AXI_TB PASSED` | 31 780 717 500 ps, 24 s d'hôte | `hw/reports/2026-11-19-xsim-l15-l16.log` |
| `fir_axi_tb` | `FIR_AXI_TB PASSED` | 26 346 237 500 ps, 8 s d'hôte | `hw/reports/2026-11-19-xsim-l15-l16.log` |

Le journal `2026-11-19-xsim-l14-l16.log` s'arrête pendant le lancement de `sha256_axi_tb` : le processus a été coupé. Le passage complet est le second journal. Les 1 018 vecteurs sont ceux de `hw/sim/vectors/sha256_padder_random.txt`, déjà comparés à `hashlib` en l12. Les 20 signaux FIR de l'AXI sont ceux de `hw/sim/vectors/fir_decim_random.txt`.

Rails FIR, modèle `saam.dsp.fir_fixed.filter_decimate`, 111 échantillons constants : la sortie d'indice 12 (entrée 60) et l'indice 22 valent `32767` pour l'entrée `+32767`, et `-32768` pour l'entrée `-32768`. Le banc direct compare les 23 sorties ; le banc AXI ne compare que le rail à l'indice 60.

## Horloge et ressources

Non mesurées pour le design PS7 + SHA-256 AXI + FIR AXI. `hw/vivado/build.tcl` construit encore le spike T1.9 (PS7 + `axil_reg_bringup`), pas ces deux IP. NFR-17 et NFR-18 ne sont donc pas démontrés ici.

Mesures antérieures, **autres designs**, recopiées depuis `PROGRESS.md` et non refaites aujourd'hui :

- Spike T1.9 `bringup_wrapper` : WNS +2,909 ns, WHS +0,057 ns, 357 LUT, 497 registres. Ce n'est pas le design de soutenance.
- Cœur SHA-256 seul, hors contexte, 10 ns : 1 175 LUT, 760 registres, 0 BRAM, 0 DSP, WNS +0,072 ns. Marge mince, déjà notée pour T3.21.

## Vérification de carte et co-vérification

Non faites. `hw/vectors/ptbxl/` est vide : les 5 enregistrements × 12 dérivations de AC-16.2 n'ont pas tourné. `demo.py`, `coverify.py`, `demo_step.py` et `LedgerClient` sont absents. Aucun port série n'a été ouvert. Aucun `BOOT.bin`.

## Limites

- GHDL, cocotb et cocotbext-axi n'ont pas été exécutés.
- Le dispatch C (`hw/ps_app/saam_cmd.c`) répond à INFO et refuse un CRC faux (`SAAM_CMD_HOSTCHECK PASSED`, GCC hôte). Il ne branche pas encore SHA-256 ni FIR sur la trame UART, et aucun `BOOT.bin` n'existe.
- Pas de revue à deux membres.
