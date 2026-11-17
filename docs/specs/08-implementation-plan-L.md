# SAAMSTIAHF — Plan d'implémentation du rôle L (itératif et incrémental)

| Owner | Status | Version | Last updated | Suite version |
|---|---|---|---|---|
| Nasr Siala (L) | Draft — à relire par un autre membre (A-02.3) | 1.0.0 | 2026-11-09 | 2.1.4 |

Ce document découpe les tâches du rôle **L — Ledger & matériel** du [plan 08](08-implementation-plan.md) en incréments livrables. Il ne change ni les tâches, ni leurs critères de fin (DoD), ni les dates officielles du plan 08 : en cas de conflit, le plan 08 et les décisions de [review.md](review.md) l'emportent (D-18 : plan inchangé, risque de calendrier accepté).

## 1. Sources et périmètre

| Document | Fait foi sur |
|---|---|
| [08-implementation-plan.md](08-implementation-plan.md) | Tâches de L (T-ID), DoD, dépendances, dates officielles |
| [03-architecture.md](03-architecture.md) | Composants SVC-ledger-gateway, SVC-chaincode, SVC-hw-sha256, SVC-hw-fir, SVC-ps-app ; interfaces IF-09, IF-10, IF-14, IF-15, IF-16 ; contrats matériels §5.6 ; règles de dépendance §6 |
| [04-backend-schema.md](04-backend-schema.md) | Enregistrements on-chain `ARTIFACT` et `MODEL` (§5.2) |
| [05-system-design.md](05-system-design.md) | Budgets de latence (DF-01 : ≤ 7,3 s par ancrage), modes de défaillance FM-01 à FM-04, FM-14 à FM-17 |
| [02-trd.md](02-trd.md) | API de la passerelle (§8.2), chaincode (§8.3), NFR-03, NFR-06, NFR-16 à NFR-20 |
| [01-prd.md](01-prd.md) | US-15, US-16, US-17 et leurs AC |

**Périmètre :** les 18 tâches de L (T1.3, T1.4, T1.8, T1.9, T2.5a, T2.5b, T2.6, T2.9, T3.18, T3.19, T3.20, T3.21, T4.12, T4.14, T5.5, T5.8, T6.1, T6.5) plus la part de L des deux tâches communes (T6.2, T6.3) : **17,6 jours**, comme au plan 08 §3. Aucune coupe (D-18). Les tâches de B, I et F restent dans le plan 08.

## 2. Méthode : itératif et incrémental

- **Incrément** : le plus petit lot qui laisse le dépôt dans un état qui marche, testé et démontrable. Il dure au plus 1 jour. Il s'appuie sur les incréments précédents et ne les casse pas.
- **Nom d'incrément = nom de branche Git** : `l<nn>-<slug>`, en minuscules, chiffres et tirets (exemple : `l04-chaincode-create-get`). Un nom ne sert qu'une fois.
- **Itération** : une série d'incréments avec un objectif et un point de revue le vendredi (A-02.5). On y met à jour [PROGRESS.md](../../PROGRESS.md) et le tableau de suivi du §5. Les AAR restent aux checkpoints de jalon du plan 08 (§8) : la part de L de M1 est l01, l02, l03 et l10 ; celle de M2 est l04 à l09.
- **Ordre** :
  1. Débloquer B d'abord. La chaîne Fabric (l01, l02, l04, l05) ouvre T2.7 puis T3.3 (ancrage) et T3.17 de B.
  2. Risque d'abord : réseau Fabric et identités avant tout ; la carte (l10) dès que la chaîne de B est ouverte, car elle ne bloque personne avant T3.21.
  3. Simulation avant matériel : SHA-256, FIR et AXI sont prouvés sous GHDL avant le bitstream et la carte.
  4. Intégration à la fin : bitstream, protocole, carte, co-vérification, clôture.

## 3. Règles de livraison par incrément (D-19)

Après chaque incrément, dans cet ordre. Aucun incrément n'est commité sans ses tests.

1. **Créer les tests** de l'incrément, de trois sortes :
   - **Tests des nouvelles fonctions** : au moins un test par ligne de « Fini quand » et par AC ou NFR cité.
   - **Tests de régression** : relancer toute la suite L (§4) et, pour chaque bug corrigé ou chaque contrat touché (schéma on-chain, carte de registres, trame UART, vecteurs de référence), ajouter un test qui le fige.
   - **Tests mis à jour** : adapter les tests des incréments précédents que l'incrément change légitimement (nouvelle interface, nouveau code d'erreur). Ne jamais supprimer, ignorer ou affaiblir un test : si c'est nécessaire, s'arrêter et demander (AGENTS.md).
2. **Lancer la suite L complète** et la vérification de l'incrément. Tout doit être vert.
3. **Commit** (Conventional Commits) : `<type>(<incrément>): <résumé> [<tâche>]`, par exemple `feat(l04-chaincode-create-get): création et lecture d'un enregistrement [T2.5a]`.
4. **Push sur une branche qui porte exactement le nom de l'incrément.** On la crée au début de l'incrément : `git switch -c l04-chaincode-create-get origin/main`. On la publie à la fin : `git push -u origin l04-chaincode-create-get`.
5. **Créer la merge request vers `main`** (pull request GitHub) :
   `gh pr create --base main --head l04-chaincode-create-get --title "l04-chaincode-create-get: <résumé>" --body "<corps>"`
   Sans `gh` : ouvrir le lien affiché par `git push`, ou « Compare & pull request » sur GitHub, avec base = `main`.
6. **Mettre à jour `PROGRESS.md`** (Fait, preuve, décisions, problèmes) et le tableau de suivi du §5.

**Corps de la merge request :**

```text
## Incrément
<nom> — <tâche(s)> — <taille>

## Contenu
<ce qui est livré, en 3 à 5 lignes>

## Couverture
<AC, NFR, ADR, IF, FM concernés>

## Tests
- Nouveaux : <fichiers et ce qu'ils prouvent>
- Régression : <commande de la suite L> → <résultat>
- Mis à jour : <tests modifiés et pourquoi> (ou « aucun »)

## Preuves
<sortie des commandes, rapports>

## Dépend de
<merge request ou tâche externe> (ou « rien »)
```

**Enchaînement.** L'incrément suivant part de `main` à jour. Si la merge request précédente n'est pas fusionnée et que l'incrément en dépend, on part de sa branche et on l'écrit dans « Dépend de ». On ne fusionne pas soi-même : un autre membre relit (AGENTS.md) et la CI est verte (quand T1.2 existe). Avant T1.2, la sortie des tests locaux dans la merge request sert de preuve.

## 4. Suite de tests de L

La suite L réunit tous les tests de L. Le script `scripts/test-l.sh` est créé par `l01-fabric-network` ; chaque incrément y ajoute ses tests.

| Type de test | Outil | Dossier | Quand il tourne |
|---|---|---|---|
| Scripts réseau et identités, latence | pytest, marqueur `fabric` | `tests/fabric/` | Réseau Fabric démarré (`--fabric`) |
| Chaincode, unitaire | Jest et simulateur fabric-shim | `chaincode/provenance/test/` | Toujours |
| Chaincode et passerelle, intégration | Jest contre le test-network | `chaincode/provenance/test/`, `ledger-gateway/test/` | `--fabric` |
| Passerelle, unitaire | Jest | `ledger-gateway/test/` | Toujours |
| Garde-fou sans données de santé | pytest | `tests/integrity/` | `--fabric` |
| VHDL en simulation | cocotb, cocotbext-axi, GHDL | `hw/sim/` | Toujours (`make -C hw/sim`) |
| Protocole UART avec modèle du PS | pytest | `hw/host/tests/` | Toujours |
| Carte Zybo Z7-10 | pytest, marqueur `board`, pyserial | `hw/host/tests/` | Carte branchée (`--board`) |
| Rapports Vivado | pytest | `hw/vivado/tests/` | Après un build |

Commandes : `./scripts/test-l.sh` (sans réseau ni carte), `./scripts/test-l.sh --fabric`, `./scripts/test-l.sh --fabric --board` (suite complète). Une merge request indique laquelle elle a lancée. La carte appartient à l'équipe (D-14) : le jeu complet est la référence dès l10.

Aucun nouvel outil hors du TRD §18 : pytest, Jest, cocotb, cocotbext-axi, GHDL, pyserial en font partie.

## 5. Incréments et suivi

Dates cibles : au rythme de **5 jours par semaine à partir du mardi 10/11/2026**, sans temps de relecture ni d'attente de dépendance. Les cibles sont indicatives ; les dates officielles restent celles du plan 08 §7. Statuts : à faire, en cours, MR ouverte, fusionné.

### Itération 1 — Chaîne Fabric prouvée (10/11 → 13/11)

| Incrément (= branche) | Tâche | Jours | Cumul | Fin cible | Statut | MR |
|---|---|---|---|---|---|---|
| `l01-fabric-network` | T1.3 | 1,0 | 1,0 | 10/11 | à faire | — |
| `l02-agent-identities` | T1.4 | 1,0 | 2,0 | 11/11 | à faire | — |
| `l03-latency-baseline` | T1.8 | 0,5 | 2,5 | 12/11 | à faire | — |
| `l04-chaincode-create-get` | T2.5a (1/2) | 1,0 | 3,5 | 13/11 | à faire | — |
| `l05-gateway-artifact-routes` | T2.6 (1/2) | 0,5 | 4,0 | 13/11 | à faire | — |

Objectif : un artefact écrit puis relu sur la chaîne, signé par l'identité d'un agent. À la fusion de `l05`, B peut démarrer T2.7.

### Itération 2 — Chaincode complet, passerelle complète, carte, premier cœur (16/11 → 20/11)

| Incrément (= branche) | Tâche | Jours | Cumul | Fin cible | Statut | MR |
|---|---|---|---|---|---|---|
| `l06-chaincode-provenance-rules` | T2.5a (2/2) | 1,0 | 5,0 | 16/11 | à faire | — |
| `l07-chaincode-model-registry` | T2.5b | 0,5 | 5,5 | 17/11 | à faire | — |
| `l08-gateway-history-model-routes` | T2.6 (2/2) | 0,5 | 6,0 | 17/11 | à faire | — |
| `l09-no-phi-guard` | T2.9 | 0,5 | 6,5 | 18/11 | à faire | — |
| `l10-board-bringup` | T1.9 | 1,0 | 7,5 | 19/11 | à faire | — |
| `l11-sha256-compress-core` | T3.18 (1/2) | 1,0 | 8,5 | 20/11 | à faire | — |

Objectif : toute la partie Fabric (M2 côté L) terminée, la carte démarre, le premier bloc de calcul SHA-256 est prouvé en simulation.

### Itération 3 — Matériel en simulation, bitstream, protocole (23/11 → 27/11)

| Incrément (= branche) | Tâche | Jours | Cumul | Fin cible | Statut | MR |
|---|---|---|---|---|---|---|
| `l12-sha256-padder-multiblock` | T3.18 (2/2) | 1,0 | 9,5 | 23/11 | à faire | — |
| `l13-fir-mac-core` | T3.19 (1/2) | 1,0 | 10,5 | 24/11 | à faire | — |
| `l14-fir-extremes-ptbxl` | T3.19 (2/2) | 1,0 | 11,5 | 25/11 | à faire | — |
| `l15-sha256-axi` | T3.20 (1/2) | 0,5 | 12,0 | 25/11 | à faire | — |
| `l16-fir-axi` | T3.20 (2/2) | 0,5 | 12,5 | 26/11 | à faire | — |
| `l17-vivado-bitstream` | T3.21 | 1,0 | 13,5 | 27/11 | à faire | — |
| `l18-uart-protocol-host` | T4.12 (1/2) | 0,5 | 14,0 | 27/11 | à faire | — |

Objectif : SHA-256 et FIR bit-exacts en simulation, bitstream qui tient 100 MHz, protocole UART prouvé contre un modèle du PS.

### Itération 4 — Carte de bout en bout (30/11)

| Incrément (= branche) | Tâche | Jours | Cumul | Fin cible | Statut | MR |
|---|---|---|---|---|---|---|
| `l19-ps-app-board` | T4.12 (2/2) | 0,5 | 14,5 | 30/11 | à faire | — |
| `l20-board-coverification-case` | T4.14 | 0,5 | 15,0 | 30/11 | à faire | — |

Objectif : la carte recalcule les empreintes et le filtrage d'un cas réel.

### Clôture — au-delà du 30/11 à ce rythme

| Incrément (= branche) | Tâche | Jours | Cumul | Fin à ce rythme | Statut | MR |
|---|---|---|---|---|---|---|
| `l21-security-review` | T5.5 | 0,5 | 15,5 | 01/12 | à faire | — |
| `l22-hw-clean-rebuild-regression` | T5.8 | 0,5 | 16,0 | 01/12 | à faire | — |
| `l23-demo-machine-offline` | T6.1 | 0,5 | 16,5 | 02/12 | à faire | — |
| `l24-demo-board-ready` | T6.5 | 0,5 | 17,0 | 02/12 | à faire | — |
| `l25-report-hardware-chapter` | T6.2 (part de L) | 0,5 | 17,5 | 03/12 | à faire | — |
| `l26-demo-rehearsals` | T6.3 (part de L) | 0,125 | 17,625 | 03/12 | à faire | — |

## 6. Détail des incréments

Chaque bloc donne ce que l'incrément livre, ses entrées, ses tests (nouveaux, de régression, mis à jour) et sa condition de fin. Les tests de régression sont toujours la suite L complète du §4 au moment de l'incrément ; ils sont listés ici seulement quand ils ajoutent quelque chose de précis.

### l01-fabric-network — T1.3
- **Livre :** `fabric/network.sh` (démarrer, arrêter, état) : test-network à 2 organisations (Org1 plateforme, Org2 audit), orderer Raft, 1 pair et 1 CA par organisation, canal `medtrace`, état LevelDB. `scripts/test-l.sh` et les marqueurs pytest `fabric` et `board`.
- **Entrées :** TRD §5, ADR-10, Architecture §10. **Dépend de :** T1.1 (B) ; s'il manque, l01 crée seulement `fabric/`, `chaincode/provenance/`, `ledger-gateway/`, `hw/` et B ajoute le reste.
- **Tests nouveaux :** `tests/fabric/test_network.py` : après le démarrage, `peer channel list` contient `medtrace` et les 2 pairs ont rejoint ; l'arrêt supprime conteneurs et volumes ; 3 cycles démarrer/arrêter de suite sans résidu. Test de `test-l.sh` : aide, codes de sortie.
- **Régression :** amorce de la suite (ces tests). **Mis à jour :** aucun.
- **Fini quand :** réseau levé et détruit 3 fois de suite (DoD de T1.3). Le test sur un second poste se fait avec un autre membre (A-02.3).

### l02-agent-identities — T1.4
- **Livre :** `fabric/enroll-identities.sh` : 7 agents (`role=pipeline-agent`, attribut `agent`), `verifier` (Org2, sans écriture), `model-admin` ; wallet hors git ; passerelle Node minimale et chaincode de démo qui lit l'attribut ; `npm run spike:submit`.
- **Entrées :** ADR-02, ADR-09, TRD §9. **Dépend de :** l01.
- **Tests nouveaux :** `tests/fabric/test_identities.py` : 9 identités enrôlées avec les bons attributs (lus dans le certificat) ; une transaction signée par `agent-ingestion` est acceptée ; une écriture signée par `verifier` est refusée ; aucun fichier du wallet dans `git ls-files`.
- **Régression :** suite L `--fabric`. **Mis à jour :** `test_network.py` : l'arrêt nettoie aussi les identités et le wallet.
- **Fini quand :** transaction de test signée par `agent-ingestion`, le chaincode lit l'attribut (DoD de T1.4).

### l03-latency-baseline — T1.8
- **Livre :** `npm run spike:latency` : 7 transactions séquentielles avec endossement `AND(Org1, Org2)`, p50, p95 et maximum ; résultat consigné dans PROGRESS.md (Décisions) ; décision sur `BatchTimeout` si le p95 dépasse 7,3 s.
- **Entrées :** NFR-01, System Design DF-01. **Dépend de :** l02.
- **Tests nouveaux :** `tests/fabric/test_latency_budget.py` : les 7 transactions sont validées ; p95 ≤ 7,3 s (garde-fou de performance) ; le rapport JSON contient p50, p95, maximum.
- **Régression :** suite L `--fabric`. **Mis à jour :** aucun.
- **Fini quand :** mesure consignée (DoD de T1.8).

### l04-chaincode-create-get — T2.5a (1/2)
- **Livre :** `chaincode/provenance/` en TypeScript : `CreateArtifactRecord`, `GetArtifactRecord`, schéma fermé de Schema §5.2, refus de doublon, `fabric/deploy-chaincode.sh`. Remplace le chaincode de démo.
- **Entrées :** TRD §8.3, Schema §5.2, AC-07.3, NFR-03. **Dépend de :** l02.
- **Tests nouveaux :** Jest unitaire : création valide ; doublon refusé (AC-07.3) ; champ inconnu refusé (NFR-03) ; `sha256` mal formé refusé ; `artifactType` hors liste refusé. Intégration : création puis lecture sur le réseau.
- **Régression :** suite L `--fabric`, latence remesurée avec le vrai chaincode. **Mis à jour :** `spike:submit` et `test_identities.py` (la transaction de test passe par `CreateArtifactRecord`) ; `test_latency_budget.py` (appelle le vrai chaincode).
- **Fini quand :** création et lecture OK, doublon et champ inconnu refusés.

### l05-gateway-artifact-routes — T2.6 (1/2)
- **Livre :** `ledger-gateway/` (Fastify, TypeScript strict) : `POST /ledger/artifacts`, `GET /ledger/artifacts/{id}`, `X-Agent-Token` vers l'identité Fabric, erreurs normalisées 401, 404, 409 et 502 (IF-09).
- **Entrées :** TRD §8.2, ADR-02, ADR-09, Architecture IF-09 et IF-10. **Dépend de :** l04 (dépendance de T2.6 affinée : la route de création n'a besoin que de la création et de la lecture).
- **Tests nouveaux :** Jest unitaire : jeton vers identité, jeton inconnu → 401. Intégration : écriture puis lecture ; doublon → 409 ; pair arrêté → 502 ; forme d'erreur normalisée.
- **Régression :** suite L `--fabric`. **Mis à jour :** `spike:submit` bascule vers la vraie passerelle et devient un test d'intégration.
- **Fini quand :** tests d'intégration verts contre le test-network. **Déblocage :** B démarre T2.7 (`LedgerClient`).

### l06-chaincode-provenance-rules — T2.5a (2/2)
- **Livre :** parent existant et du même `caseId` (NFR-06) ; `original` sans parent ; refus sans `role=pipeline-agent` ; `creatorMspId`, `creatorId`, `creatorAgent` pris dans le certificat, jamais chez le client ; `txTimestamp` ; `GetCaseHistory` (clé composite `case~artifact`) ; événement `ArtifactAnchored`.
- **Entrées :** TRD §8.3, Schema §5.2, NFR-06, ADR-10. **Dépend de :** l04.
- **Tests nouveaux :** Jest : parent absent refusé ; parent d'un autre cas refusé ; type non `original` sans parent refusé ; appel sans attribut refusé ; champs `creator*` fournis par le client refusés ; historique ordonné parent vers enfant ; événement émis. Intégration : chaîne de 7 artefacts, `GetCaseHistory` en renvoie 7.
- **Régression :** suite L `--fabric`. **Mis à jour :** les cas valides de l04 reçoivent un parent selon les nouvelles règles ; la lecture par la passerelle renvoie `creator*`.
- **Fini quand :** tests de DoD de T2.5a verts (doublon, parent absent, champ inconnu, sans attribut, `creator*` du certificat).

### l07-chaincode-model-registry — T2.5b
- **Livre :** `RegisterModel`, `GetModel` (clé composite nom + version), attribut `role=model-admin`, refus de doublon.
- **Entrées :** Schema §5.2 (MODEL), AC-04.3. **Dépend de :** l06.
- **Tests nouveaux :** attribut `model-admin` requis ; doublon refusé ; lecture d'un modèle absent → erreur typée ; schéma fermé.
- **Régression :** suite L `--fabric`. **Mis à jour :** test de déploiement (la séquence du chaincode augmente).
- **Fini quand :** attribut requis, doublon refusé (DoD de T2.5b).

### l08-gateway-history-model-routes — T2.6 (2/2)
- **Livre :** `GET /ledger/cases/{caseId}`, `POST /ledger/models`, `GET /ledger/models/{name}/{version}` ; code d'erreur 403 quand le chaincode refuse (`FORBIDDEN`).
- **Entrées :** TRD §8.2, Architecture IF-09. **Dépend de :** l06, l07.
- **Tests nouveaux :** intégration : historique de 7 artefacts ; enregistrement de modèle avec un jeton non admin → 403 ; lecture d'un modèle.
- **Régression :** suite L `--fabric`. **Mis à jour :** test de forme d'erreur (nouveau code 403).
- **Fini quand :** les 5 routes passent les tests d'intégration (DoD de T2.6).

### l09-no-phi-guard — T2.9
- **Livre :** `tests/integrity/test_no_phi_onchain.py` : parcourt `GetCaseHistory` d'un cas factice, refuse tout champ hors schéma et tout motif de nom ou de date de naissance.
- **Entrées :** NFR-03. **Dépend de :** l08 ; T2.7 (B) pour `LedgerClient` — sans lui, le test appelle la passerelle avec `httpx`.
- **Tests nouveaux :** données factices propres → vert ; enregistrement avec un champ interdit ou un motif de date → détecté (test négatif).
- **Régression :** suite L `--fabric`. **Mis à jour :** quand T2.7 arrive, le client `httpx` du test est remplacé par `LedgerClient`.
- **Fini quand :** test vert sur données factices (DoD de T2.9).

### l10-board-bringup — T1.9
- **Livre :** `hw/vivado/build.tcl` minimal (PS7 + 1 registre AXI4-Lite) avec les fichiers de carte Digilent, application Vitis « hello » sur l'UART, `BOOT.bin` sur carte SD, essai à 921 600 bauds. Réponse à Q-14 (licence Vivado, fichiers de carte).
- **Entrées :** Architecture §5.6 (Intégration Zynq), ADR-13, D-12, Q-14. **Dépend de :** T1.1 (B).
- **Tests nouveaux :** `hw/host/tests/test_bringup.py` (marqueur `board`) : lit « hello » sur le port série ; écrit puis relit un registre ; mesure le débit effectif à 115 200 et à 921 600 bauds.
- **Régression :** suite L `--fabric --board`. **Mis à jour :** `test-l.sh` gagne `--board`.
- **Fini quand :** registre écrit et relu depuis le PS, démarrage depuis la SD, débit UART consigné dans PROGRESS.md (DoD de T1.9).

### l11-sha256-compress-core — T3.18 (1/2)
- **Livre :** `hw/rtl/sha256_core.vhd` (1 ronde par cycle, registre à décalage de 16 mots) ; `hw/sim/Makefile` GHDL + cocotb ; banc `hw/sim/test_sha256.py` pour des blocs déjà bourrés.
- **Entrées :** US-15 (AC-15.1), Architecture §5.6, ADR-12. **Dépend de :** T1.10 (B) ; sinon un Makefile GHDL local minimal, B ajoute le job CI.
- **Tests nouveaux :** cocotb : vecteurs FIPS 180-4 pré-bourrés (« abc », 448 bits, 896 bits) comparés à `hashlib` ; 2 messages de suite ; reprise après reset ; durée d'un bloc.
- **Régression :** `make -C hw/sim` entre dans `test-l.sh`. **Mis à jour :** aucun.
- **Fini quand :** les blocs de référence sont identiques à `hashlib`.

### l12-sha256-padder-multiblock — T3.18 (2/2)
- **Livre :** `hw/rtl/sha256_padder.vhd` : bourrage FIPS en matériel, messages de 0 à 4 096 octets.
- **Entrées :** US-15 (AC-15.1, AC-15.2). **Dépend de :** l11.
- **Tests nouveaux :** message vide et « abc » (AC-15.1) ; 1 000 messages aléatoires de 0 à 4 096 octets, graine fixe ; longueurs 55, 56, 63, 64, 119 et 120 octets (AC-15.2) ; 100 % identiques à `hashlib`.
- **Régression :** suite L. **Mis à jour :** `test_sha256.py` de l11 passe par le bourreur (flux de mots et octets valides du dernier mot).
- **Fini quand :** 100 % identiques à `hashlib` (DoD de T3.18).

### l13-fir-mac-core — T3.19 (1/2)
- **Livre :** `hw/rtl/fir_decim.vhd` avec le paquet `fir_coeffs_pkg.vhd` généré par I ; 1 MAC séquentielle, ligne à retard de 111 échantillons, décimation ×5 ; banc `hw/sim/test_fir.py`.
- **Entrées :** US-16 (AC-16.2), Architecture §5.6 (FIR), ADR-14. **Dépend de :** T2.10 (I : `fir_fixed.py`, coefficients), T1.10.
- **Tests nouveaux :** sortie bit-exacte contre `saam/dsp/fir_fixed.py` sur 20 signaux int16 aléatoires ; remise à zéro entre deux dérivations ; 1 011 sorties pour 5 055 entrées ; `fir_coef_id` du paquet = celui de `fir_coeffs.json`.
- **Régression :** suite L. **Mis à jour :** aucun.
- **Fini quand :** sortie bit-exacte sur les signaux aléatoires.

### l14-fir-extremes-ptbxl — T3.19 (2/2)
- **Livre :** tests aux valeurs extrêmes et sur de vrais enregistrements.
- **Entrées :** US-16 (AC-16.2, AC-16.4). **Dépend de :** l13 ; T2.11 (I : 5 enregistrements PTB-XL dans `hw/vectors/ptbxl/`).
- **Tests nouveaux :** entrées −32 768 et +32 767 saturées comme `fir_fixed.py` (AC-16.4) ; 5 enregistrements × 12 dérivations bit-exacts (AC-16.2).
- **Régression :** suite L. **Mis à jour :** aucun. Un changement de coefficients impose une nouvelle `fir_coef_id` et de s'arrêter pour demander (AGENTS.md).
- **Fini quand :** sortie bit-exacte contre `fir_fixed.py` (DoD de T3.19).

### l15-sha256-axi — T3.20 (1/2)
- **Livre :** `hw/rtl/sha256_axi.vhd` (AXI4-Lite : CTRL, STATUS, DATA_IN, LAST_BYTES, DIGEST0–7, VERSION).
- **Entrées :** Architecture §5.6 (carte de registres SHA-256), IF-15. **Dépend de :** l12.
- **Tests nouveaux :** cocotbext-axi : offsets et bits conformes au tableau ; mêmes vecteurs que l12 via AXI ; STATUS (READY, BUSY, DONE) ; écriture dans un registre en lecture seule sans effet.
- **Régression :** suite L. **Mis à jour :** `test_sha256.py` : vecteurs factorisés entre accès direct et AXI.
- **Fini quand :** accès conformes à la carte de registres, mêmes vecteurs via AXI.

### l16-fir-axi — T3.20 (2/2)
- **Livre :** `hw/rtl/fir_axi.vhd` (CTRL CLEAR, STATUS, DATA_IN, DATA_OUT, COEF_ID, VERSION).
- **Entrées :** Architecture §5.6 (carte de registres FIR), IF-16. **Dépend de :** l14, l15.
- **Tests nouveaux :** offsets et bits ; mêmes vecteurs que l13 et l14 via AXI ; la lecture de DATA_OUT consomme la sortie ; COEF_ID lisible.
- **Régression :** suite L. **Mis à jour :** `test_fir.py` : vecteurs factorisés.
- **Fini quand :** accès conformes, mêmes vecteurs via AXI (DoD de T3.20).

### l17-vivado-bitstream — T3.21
- **Livre :** `hw/vivado/build.tcl` complet (PS7 + 2 IP, FCLK0 100 MHz) : bitstream, XSA, rapports d'utilisation et de timing dans `hw/reports/` ; registre VERSION = SHA git.
- **Entrées :** NFR-17, NFR-18, NFR-19, Architecture §5.6 (Intégration Zynq). **Dépend de :** l10, l16.
- **Tests nouveaux :** `hw/vivado/tests/test_reports.py` : WNS ≥ 0 à 100 MHz (NFR-17) ; utilisation ≤ 50 % des LUT, FF, BRAM, DSP (NFR-18) ; VERSION = SHA git ; le script s'exécute sans étape manuelle (NFR-19). Tourne en local : Vivado n'est pas en CI (TRD §17).
- **Régression :** suite L `--board`. **Mis à jour :** `test_bringup.py` : le registre de test est remplacé par les registres VERSION des 2 IP.
- **Fini quand :** WNS ≥ 0, ressources consignées contre NFR-18 (DoD de T3.21).

### l18-uart-protocol-host — T4.12 (1/2)
- **Livre :** `hw/host/zybo_client.py` (trames `0xA5`, commande, longueur, charge, CRC-32 ; commandes INFO, SHA256, FIR ; 3 réessais sur CRC invalide) et `hw/host/ps_model.py`, un modèle logiciel du PS pour tester sans carte.
- **Entrées :** Architecture §5.6 (protocole UART), ADR-13, IF-14. **Dépend de :** l17.
- **Tests nouveaux :** encodage et décodage de trames ; CRC invalide rejeté ; 3 réessais puis « Erreur de transmission » ; INFO ; SHA256 de « abc » contre le modèle ; FIR contre `fir_fixed.py`.
- **Régression :** suite L sans carte. **Mis à jour :** aucun.
- **Fini quand :** protocole conforme sur le modèle du PS.

### l19-ps-app-board — T4.12 (2/2)
- **Livre :** `hw/ps_app/` (Vitis, C bare-metal : boucle de commandes, pilotes des 2 IP) et `BOOT.bin` sur SD.
- **Entrées :** Architecture §5.6, ADR-13, IF-14, IF-15, IF-16. **Dépend de :** l17, l18.
- **Tests nouveaux :** `hw/host/tests -m board` : INFO renvoie VERSION et COEF_ID ; « abc » donne le condensat FIPS sur la carte ; CRC invalide rejeté ; FIR d'une dérivation identique au modèle.
- **Régression :** suite L `--fabric --board`. **Mis à jour :** les tests de l18 tournent aussi contre la carte (même suite, deux cibles : modèle et carte).
- **Fini quand :** tests de DoD de T4.12 verts sur la carte.

### l20-board-coverification-case — T4.14
- **Livre :** co-vérification N2 sur le cas de démonstration (`demo.py --record 00001`) : rapport `hw/reports/<date>-board-<cas>.md`.
- **Entrées :** US-15 (AC-15.3, AC-15.4), US-16 (AC-16.3), NFR-16. **Dépend de :** l19 ; T4.13 (I : `coverify.py`, `demo_step.py`), T4.8 (B : `demo.py`).
- **Tests nouveaux :** 7 empreintes sur 7 identiques à celles du registre ; 12 dérivations sur 12 identiques à `processed` ; manifeste modifié d'un octet → « DIFFÉRENT » (AC-15.4) ; carte débranchée → code de sortie 2, aucun verdict « identique ».
- **Régression :** suite L `--fabric --board`. **Mis à jour :** aucun.
- **Fini quand :** 7/7 et 12/12 identiques, falsification détectée (DoD de T4.14).

### l21-security-review — T5.5
- **Livre :** checklist de sécurité remplie dans la merge request (OWASP, secrets, NFR-03, privilèges) ; problèmes consignés dans review.md et corrigés.
- **Entrées :** TRD §12. **Dépend de :** T4.11 (B).
- **Tests nouveaux :** `pip-audit` et `npm audit` (chaincode, passerelle) sans vulnérabilité haute ; `git ls-files` sans wallet, `.env` ni clé ; le chaincode refuse chaque champ interdit (rejoué).
- **Régression :** suite L complète. **Mis à jour :** `test_no_phi_onchain.py` si de nouveaux motifs sont ajoutés.
- **Fini quand :** checklist remplie, problèmes corrigés (DoD de T5.5).

### l22-hw-clean-rebuild-regression — T5.8
- **Livre :** reconstruction depuis un clone propre, N1 et N2 complets, mesures de timing, de ressources et de durée de l'étape 9 consignées pour le rapport.
- **Entrées :** NFR-16, NFR-17, NFR-18, NFR-19, NFR-20. **Dépend de :** l20.
- **Tests nouveaux :** build depuis un clone frais sans étape manuelle (sortie 0) ; mêmes résultats N1 et N2 qu'avant ; assertions NFR-17 à NFR-20 sur les rapports.
- **Régression :** suite L complète. **Mis à jour :** rapports de référence de `hw/reports/`.
- **Fini quand :** critères tenus, ou problème ouvert avec décision (DoD de T5.8).

### l23-demo-machine-offline — T6.1
- **Livre :** machine de démonstration avec images Docker pré-tirées (`docker save`), fonctionnement hors ligne.
- **Entrées :** TRD §17, Q-03. **Dépend de :** T5.7 (B).
- **Tests nouveaux :** démonstration complète réseau coupé (`demo.py` hors ligne).
- **Régression :** suite L complète. **Mis à jour :** aucun.
- **Fini quand :** démonstration complète sans réseau (DoD de T6.1).

### l24-demo-board-ready — T6.5
- **Livre :** `BOOT.bin` final sur SD et sur une SD de secours ; vidéo de secours de l'étape 9.
- **Entrées :** D-13, PRD §14. **Dépend de :** l22.
- **Tests nouveaux :** démarrage depuis chacune des 2 SD sans Vivado ; `demo_step.py` réussit avec chacune ; la vidéo se lit hors ligne.
- **Régression :** suite L `--board`. **Mis à jour :** aucun.
- **Fini quand :** démarrage SD sans PC Vivado, vidéo lisible hors ligne (DoD de T6.5).

### l25-report-hardware-chapter — T6.2 (part de L)
- **Livre :** chapitre matériel du rapport final : architecture, ressources, timing, co-vérification.
- **Entrées :** CDC §12, PRD §17. **Dépend de :** T5.4 (I), l22.
- **Tests :** pas de code : relecture par 2 membres ; chaque chiffre du chapitre recoupé avec `hw/reports/`.
- **Régression :** suite L complète. **Mis à jour :** aucun.
- **Fini quand :** relu par 2 membres (DoD de T6.2).

### l26-demo-rehearsals — T6.3 (part de L)
- **Livre :** présence de L aux 2 répétitions chronométrées, étape 9 incluse.
- **Entrées :** CDC §9, D-13. **Dépend de :** l23, l24.
- **Tests :** grille de répétition : 9 étapes sur 9 réussies.
- **Régression :** suite L complète. **Mis à jour :** aucun.
- **Fini quand :** 9/9 étapes réussies (DoD de T6.3).

## 7. Dépendances externes

| Besoin | Fourni par | Nécessaire le | Si absent |
|---|---|---|---|
| Squelette du dépôt (T1.1) | B | 10/11 (l01) | l01 crée seulement les dossiers de L ; B ajoute le reste |
| Relecteurs nommés (A-02.3) | Équipe | 10/11 (première merge request) | La merge request s'ouvre, mais ne peut pas être fusionnée sans relecteur (AGENTS.md) |
| CI GitHub (T1.2) | B | 13/11 (l05) | Sortie des tests locaux dans la merge request |
| `LedgerClient` (T2.7) | B | 18/11 (l09) | Le test appelle la passerelle avec `httpx` |
| Job CI `hw-sim` et GHDL (T1.10) | B | 19/11 (l11) | Makefile GHDL local minimal ; B ajoute le job CI |
| `fir_fixed.py` et coefficients (T2.10) | I | 23/11 (l13) | l13 attend ; l15 peut passer avant |
| Enregistrements PTB-XL (T2.11) | I | 24/11 (l14) | l14 attend |
| `coverify.py` et `demo_step.py` (T4.13), `demo.py` (T4.8) | I, B | 30/11 (l20) | l20 attend |
| Événements d'audit (T4.11), sauvegarde (T5.7) | B | l21, l23 | l21 et l23 attendent |

## 8. Capacité et ligne du 30/11

| | Jours |
|---|---|
| Travail de L (18 tâches + parts de T6.2 et T6.3) | 17,6 |
| Jours ouvrés du 10/11 au 30/11 (5 jours par semaine) | 15 |
| Jours ouvrés à 4 jours par semaine | 12 |
| Écart à 5 jours par semaine | 2,6 |
| Écart à 4 jours par semaine | 5,6 |

- À 5 jours par semaine, les incréments **l01 à l20** (15,0 j) tiennent jusqu'au 30/11. Les incréments **l21 à l26** (2,6 j) tombent après la soutenance : sécurité, reconstruction propre, machine et carte de démonstration, chapitre du rapport, répétitions.
- Le temps de relecture, d'attente de dépendance et de cérémonie de livraison (tests, commit, push, merge request) n'est pas compté ici : `[TBD: à mesurer sur l01]`.
- Les chiffres de l'AAR-02 (16 jours ouvrés, 13 j à 4 jours par semaine, écart de 4,6 j) comptaient le 09/11 ; ce plan démarre le 10/11, car le 09/11 sert à le préparer.
- La porte M6 est le 27/11 : à ce rythme, L a terminé jusqu'à l18 (14,0 j) ce jour-là. Restent l19 à l26 (3,6 j).
- D-18 garde le périmètre et les dates. La liste de coupes du plan 08 §2 reste la seule soupape, sur décision de l'utilisateur.

## 9. Risques propres à ce plan

| Risque | Probabilité | Impact | Mitigation |
|---|---|---|---|
| Fabric sous Windows : les scripts du test-network sont en bash | Moyenne | Élevé | Travailler dans WSL2 ; Docker Desktop démarré (le démon était arrêté lors de la vérification du 2026-10-05) ; `[TBD: valider en l01]` |
| Aucun relecteur nommé : les merge requests s'accumulent | Élevée | Élevé | Fermer A-02.3 avant la première merge request |
| `gh` absent de ce poste (vérifié le 2026-11-09) | Certaine | Faible | `winget install GitHub.cli` puis `gh auth login`, ou créer la merge request sur le site GitHub |
| GHDL sous Windows | Moyenne | Moyen | Paquet MSYS2 ou WSL2 ; la CI (T1.10) tourne sous Linux `[TBD: valider en l11]` |
| La carte ne démarre pas (T1.9) | Faible | Élevé | Spike placé en l10, avec 4 jours d'avance sur l17 ; Q-14 (licence) vérifiée au même moment |
| I n'a pas livré les coefficients (T2.10) avant l13 | Élevée | Élevé | Remonter le besoin au point du vendredi 20/11 ; avancer l15 |

## 10. Hypothèses

- L travaille 5 jours par semaine du 10/11 au 30/11 ; un incrément de 1 jour tient en 1 jour avec ses tests.
- Une merge request est relue le jour même ou le lendemain par un autre membre `[TBD: A-02.3]`.
- Le protocole de livraison du §3 s'applique aussi aux incréments qui ne touchent que de la documentation ; sans code, les « tests » sont les vérifications listées dans l'incrément (l25, l26).

## 11. Questions ouvertes

Voir [review.md](review.md) : Q-11 (noms de I, B, F), Q-12 et Q-15 (encadrant, porte M2), Q-14 (licence Vivado, fichiers de carte).

## Annexe — Couverture des tâches de L

| Tâche | Incréments |
|---|---|
| T1.3 | l01 |
| T1.4 | l02 |
| T1.8 | l03 |
| T1.9 | l10 |
| T2.5a | l04, l06 |
| T2.5b | l07 |
| T2.6 | l05, l08 |
| T2.9 | l09 |
| T3.18 | l11, l12 |
| T3.19 | l13, l14 |
| T3.20 | l15, l16 |
| T3.21 | l17 |
| T4.12 | l18, l19 |
| T4.14 | l20 |
| T5.5 | l21 |
| T5.8 | l22 |
| T6.1 | l23 |
| T6.5 | l24 |
| T6.2 (part de L) | l25 |
| T6.3 (part de L) | l26 |
