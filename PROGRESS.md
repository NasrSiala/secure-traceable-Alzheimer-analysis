# PROGRESS — SAAMSTIAHF

Suite de specs : v2.1.4 (2026-11-09). Mettre à jour à la fin de chaque tâche.

## Courant

- **Jalon :** M1 — échéance 2026-10-28 dépassée ; porte M2 du 2026-11-03 non approuvée. Plan conservé tel quel, risque de calendrier accepté (D-18).
- **Équipe :** L = Nasr Siala ; I, B, F à nommer (A-02.3).
- **Plan de L :** [docs/specs/08-implementation-plan-L.md](docs/specs/08-implementation-plan-L.md) ; `l01-fabric-network` et `l02-agent-identities` sont poussés (l02 part de la branche l01, dont la merge request n'est pas fusionnée). `l03-latency-baseline` est commité sur sa branche. `l04-chaincode-create-get` est vérifié localement et n'est pas encore commité ; ses fichiers sont dans l'arbre de travail de `l03-latency-baseline` : `git switch -c l04-chaincode-create-get` avant le commit, et `git add --chmod=+x fabric/deploy-chaincode.sh fabric/scripts/deploy-chaincode.sh`.
- **État au 2026-11-10 :** `l04-chaincode-create-get` (T2.5a, 1/2) crée et relit un ARTIFACT sur `medtrace`. Remesure avec `CreateArtifactRecord` : p50 = 2,085472 s, p95 = 2,184678 s, maximum = 2,184678 s ; `BatchTimeout` reste `2s`. Aucun commit, push ni merge request de l04. Les merge requests de l01 et de l02 restent à ouvrir sur GitHub (`gh` absent) ; la MR de l02 dépend de celle de l01 et doit l'écrire. Test sur un hôte Linux natif et sur un second poste : à faire avec un autre membre (A-02.3).
- **Tâche suivante :** T2.6 `l05-gateway-artifact-routes` (L), qui débloque T2.7 de B ; `l06-chaincode-provenance-rules` (T2.5a, 2/2) dépend aussi de l04. En parallèle T1.1 (B), T1.6 (I), T1.7 (F) dès que leurs porteurs sont nommés.
- **Bloquants :** noms de I, B, F ; voir `docs/specs/review.md`.
- **Point hebdomadaire :** vendredi 13/11, 20/11, 27/11 — ce fichier à jour, y compris « rien fait » (A-02.5).

## Avancement - Role I (2026-11-15)

| Tache | Avancement | Verification / reserve |
|---|---|---|
| T2.10 - FIR fixe | Generation de 111 coefficients Q1.15, filtre multi-lead bit-exact et tests | AC-16.1 passe : ondulation quantifiee 0.3793 dB et attenuation 52.4227 dB (seuil 40 dB). NFR-21 distinct : RSB mesure 55.8255 dB global sur cinq ECG, sous 60 dB ; aucune modification du contrat ou des coefficients sans autorisation. `fir_coef_id=b6d7a73a` est maintenant calcule par `saam.hashing.artifact_hash`. |
| T2.11 - Vecteurs PTB-XL | Cinq enregistrements `records500` du fold 10 prepares dans `hw/vectors/ptbxl/records500/00000/` | `ml/data.py --check-hw-vectors` passe : cinq sources fold 10 concordent avec leurs checksums et vecteurs WFDB, ? 500 Hz, forme 5000?12, d?rivations et unit?s attendues. Attribution CC BY 4.0 pr?sente. |
| T2.12 - Preparation ECG | `saam/dsp/prepare.py` implemente et teste | ECG PTB-XL reel ECG 1 valide. Sorties : `[12,5000]`, `[12,1011]`, `[12,1000]`. Politique stricte : rejet des echantillons invalides, sans interpolation. 14 tests dedies. |
| Suite de tests | Verification globale effectuee | 112 passed, 1 skipped, 9 deselected. `git diff --check` reussi. |

## Fait

| Tâche | Date | Preuve (commande / lien) |
|---|---|---|
| T1.3 `l01-fabric-network` | 2026-11-09 | `bash -n` sur les scripts ; `py -3 -m pytest -q -o addopts= -m "not fabric and not board" tests` : 12 passed ; `py -3 -m pytest -q -o addopts= -m fabric tests` : 2 passed (3 cycles start/stop, canal `medtrace`, les deux pairs, LevelDB) ; `scripts/test-l.sh` et `scripts/test-l.sh --fabric` : exit 0. Après l'audit du 2026-11-09 : `scripts/test-l.sh` 18 passed, 1 skipped (test de permissions POSIX, ignoré sous Windows) ; `scripts/test-l.sh --fabric` : 3 passed (dont `status` sans effet de bord). Conteneurs et volumes `saam-medtrace` absents après stop. `git ls-files` ne contient aucun `.pem`, `.key`, `.crt`, `_sk`, wallet ni `ca.env`. |
| T1.4 `l02-agent-identities` | 2026-11-09 | `bash -n` sur les scripts Fabric : exit 0. `tests/fabric/test_identities.py` marqué `fabric` : 1 passed. `scripts/test-l.sh` : 19 passed, 1 skipped. `scripts/test-l.sh --fabric` : même suite locale, puis 4 passed (identités, écriture `agent-ingestion`, refus `verifier`, cycles réseau). `git diff --check` : exit 0. `fabric/wallet` et `fabric/.runtime` absents après stop ; `git check-ignore` accepte `fabric/wallet/agent-ingestion/key.pem` ; `git ls-files` ne liste aucun wallet, `.pem`, `.key`, `.crt` ni `_sk`. Aucun conteneur, volume ni réseau `saam-medtrace` restant. Le projet Fabric voisin (`orderer.example.com`, `peer0.org1.example.com`, `peer0.org2.example.com`, réseau `fabric_test`, volumes `compose_*`) est inchangé. Après l'audit du 2026-11-09 (passe 2) : Windows, `scripts/test-l.sh` 51 passed, 1 skipped, puis `tsc --noEmit` des deux paquets (Node 22) ; `scripts/test-l.sh --fabric` : 8 passed en 538 s (identités avec second enrôlement, écriture `agent-ingestion`, refus `verifier`, arrêt avec conteneur ponctuel oublié, 3 cycles, vérification TypeScript dans l'image Node). Ubuntu 22.04 sous WSL2 (ext4, uid 1000, moteur Docker Desktop) : `pytest -m fabric` 8 passed, aucun fichier root restant ; 50 passed en local, 1 échec propre à WSL2 (`test_check_ports_reports_a_busy_port`, AUD-047). `npm audit` : 0 vulnérabilité dans les deux paquets. Aucun conteneur, volume, réseau ni `fabric/wallet` restant. |
| T1.8 `l03-latency-baseline` | 2026-11-09 | `py -3 -m pytest -q -o addopts= -s -m fabric tests/fabric/test_latency_budget.py` : 1 passed en 191,84 s. Ligne `LATENCY_BASELINE` : p50 = 2,084254 s, p95 = 2,262708 s, maximum = 2,262708 s, échantillons 2,262708, 2,091003, 2,104003, 2,084254, 2,067015, 2,068252, 2,030499, `batchTimeout` = `2s`, décision `keep`. Sept codes `VALID`. `scripts/test-l.sh --fabric` : 55 passed, 1 skipped, `tsc --noEmit` des deux paquets, puis 9 passed en 727,93 s. `git diff --check` : exit 0. `fabric/wallet` absent après stop ; aucun conteneur `saam-medtrace` restant. Après l'audit du 2026-11-10 (passe 3, AUD-048 à AUD-056) : `scripts/test-l.sh` 74 passed, 1 skipped (19 tests nouveaux dans `tests/scripts/test_spike_latency_script.py`), puis `tsc --noEmit` des deux paquets ; `scripts/test-l.sh --fabric` 9 passed en 924,81 s. Mesures de contrôle sur le même réseau : le script de l'hôte, `npm run spike:latency` seul et la branche conteneur (`docker compose … spike`) donnent chacun 7 codes `VALID`, p95 = 2,237257 s, 2,214687 s et 2,129821 s. |
| T2.5a `l04-chaincode-create-get` | 2026-11-10 | Jest du chaincode : 6 passed (création puis lecture, doublon `DUPLICATE`, champ inconnu, `creatorMspId` client, `sha256` mal formé, `artifactType` hors liste). `py -3 -m pytest -q -o addopts= -s -m fabric tests/fabric/test_latency_budget.py` : 1 passed en 268,00 s. `LATENCY_BASELINE` : p50 = 2,085472 s, p95 = 2,184678 s, maximum = 2,184678 s, échantillons 2,184678, 2,055871, 2,078289, 2,061179, 2,090475, 2,087641, 2,085472, `batchTimeout` = `2s`, décision `keep`. `scripts/test-l.sh --fabric` : 74 passed, 1 skipped, Jest 6 passed, `tsc --noEmit` des deux paquets, puis 9 passed en 1000,87 s (création puis lecture, doublon, refus `verifier`). `git diff --check` : exit 0. `fabric/wallet` et `fabric/.runtime` absents ; aucun conteneur ni réseau `saam-medtrace`. Le projet voisin (`orderer.example.com`, `peer0.org1.example.com`, `peer0.org2.example.com`, réseau `fabric_test`, volumes `compose_*`) est inchangé. Après l'audit du 2026-11-10 (passe 4, AUD-057 à AUD-068) : Jest 60 passed (54 tests ajoutés : `FORBIDDEN` sous quatre formes, `NOT_FOUND`, champs réservés, bornes, formats de date, doublon sans écrasement ; contrôles par mutation : quatre mutations donnent 1 à 2 échecs, le code sain 60 passed) ; `scripts/test-l.sh` 85 passed, 1 skipped (4 tests de `fabric/deploy-chaincode.sh`, 1 test du contournement `deepmerge`, 6 tests de la relance de latence), puis `tsc --noEmit` et Jest dans l'image Node ; `scripts/test-l.sh --fabric` 9 passed en 1154,76 s (une exécution antérieure : 8 passed et le test de latence en échec à p95 = 9,0 s sur un moteur Docker qui venait de redémarrer ; AUD-068). Quatre sondes de suite sur un réseau neuf : tous les échantillons entre 2,04 s et 2,18 s. Deux exécutions de `fabric/spike-latency.sh` de suite sur le même réseau passent (branche conteneur) ; `npm audit` : 0 dans `ledger-gateway` et dans `chaincode/provenance` (6 avis faibles `deepmerge` levés par `overrides`, AUD-063). |

## Décisions (prises pendant le build)

| Date | Décision | Contexte | Reportée dans les specs ? |
|---|---|---|---|
| 2026-11-09 | D-18 : plan inchangé, aucune coupe, soutenance du 30/11 maintenue | Équipe à 0 tâche ; 64,5 j de tâches pour 64 j-personne au maximum | Oui : review.md, aar.md, Plan §12 |
| 2026-11-09 | Réseau de test isolé `saam-medtrace` (label `saam.network=medtrace`, ports hôte 18050–18056, LevelDB). Une CA d'orderer s'ajoute aux CA Org1 et Org2. `osnadmin` est lancé depuis `fabric-tools:2.5.16`. `core.yaml` du pair est extrait au démarrage dans `fabric/.runtime/` (gitignoré). | Des conteneurs Fabric d'un autre projet occupent déjà les noms et ports usuels. L'image orderer 2.5.16 n'a pas `osnadmin` ; le montage MSP masque le `core.yaml` de l'image pair. | Non : le canal, les deux organisations, Raft et LevelDB restent ceux des specs. |
| 2026-11-09 | Moindre privilège des rôles de base (`schema.sql`, suite v2.1.2) : `app_worker` sans lecture des comptes, `UPDATE` par colonnes sur `artifacts` et `validation_configs`, `DELETE` sur `login_attempts` pour `app_api` | Constats AUD-002, AUD-008, AUD-009 de l'audit ; accord de l'utilisateur | Oui : schema.sql, 04-backend-schema.md, CHANGELOG. T2.1 devra reproduire ces privilèges |
| 2026-11-09 | Table des erreurs de la passerelle (IF-09/IF-07) : 401 jeton, 403 `FORBIDDEN`, 404, 409 `DUPLICATE`, 400 `SCHEMA`, 422 `PARENT_MISSING`, 502 Fabric | Constat AUD-011 ; décidé par L (Nasr Siala) | Oui : Architecture §7, CHANGELOG v2.1.3. À confirmer par B avant T2.7 |
| 2026-11-09 | Les neuf identités sont enrôlées par `fabric-ca-client` : sept agents Org1 (`role=pipeline-agent`, attribut `agent` court), `model-admin` Org1 (`role=model-admin`, sans `agent`), `verifier` Org2 sans attribut d'écriture. Le chaincode de démo `identity-spike` lit ces attributs et refuse l'écriture sans `role=pipeline-agent`. Déploiement CCAAS, sans socket Docker sur les pairs : deux services `node:20-bookworm`, politique `AND('Org1MSP.peer','Org2MSP.peer')`. L'hôte n'a pas Node ; `tsc` et `npm ci` tournent dans cette image. Le script attend que chaque pair ouvre le port 9999 du service, et le paquet annonce `dial_timeout` 120 s. | T1.4, ADR-02, ADR-09, TRD §9. Les pairs de l01 ne montent pas `docker.sock`. | Non : les rôles et l'emplacement des organisations restent ceux des specs. Le chaincode de démo est remplacé par l04. |
| 2026-11-09 | Outillage Node ajouté au TRD §18 (`typescript`, `@types/node`, `reflect-metadata`, `jest`, `eslint`) | AUD-038 ; décidé par L (Nasr Siala) ; ces paquets découlent de la pile déjà choisie, aucune bibliothèque d'exécution n'est ajoutée | Oui : TRD v2.0.4, CHANGELOG v2.1.4. À confirmer par B (T1.1) |
| 2026-11-09 | Linux : les conteneurs Fabric tournent en root. Le nettoyage de `fabric/organizations`, `channel-artifacts`, `.runtime`, `wallet` se fait au besoin dans un conteneur `cleaner` (sans réseau) ; les fichiers du wallet et de `node_modules`/`dist` sont rendus au propriétaire du dossier ; le certificat TLS du pair est publié dans le wallet (`organizations/` n'est lisible que par root) | AUD-041, AUD-046 | Non : comportement des scripts, aucune règle de spec |
| 2026-11-09 | `BatchTimeout` reste `2s`. La mesure T1.8 donne p50 = 2,084254 s, p95 = 2,262708 s et maximum = 2,262708 s, tous sous le seuil de 7,3 s. On ne passe pas à 0,5 s. | Sept transactions séquentielles `Write` de `identity-spike`, signées par `agent-ingestion`, endossement `AND('Org1MSP.peer','Org2MSP.peer')`. Chaque durée va de l'endossement jusqu'au statut de commit `VALID` (nearest-rank : avec 7 échantillons, p95 = maximum). Échantillons en secondes : 2,262708, 2,091003, 2,104003, 2,084254, 2,067015, 2,068252, 2,030499. Poste Windows, Docker 29.9.2, Node 22.17.0. Ce n'est pas la machine de démo (Q-03). Remesures du 2026-11-10 sur un réseau neuf : p95 = 2,237257 s (script de l'hôte), 2,214687 s (`npm run spike:latency` seul), 2,129821 s (conteneur) ; même conclusion. | Non : System Design §10 ne demande 0,5 s que si le p95 dépasse 7,3 s. l04 remesure avec le chaincode de provenance. |
| 2026-11-10 | `BatchTimeout` reste `2s` après la remesure sur `provenance`. p50 = 2,085472 s, p95 = 2,184678 s, maximum = 2,184678 s, tous sous 7,3 s. | Sept `CreateArtifactRecord` séquentiels, identité `agent-ingestion`, endossement `AND('Org1MSP.peer','Org2MSP.peer')`, de l'endossement au statut `VALID`. Échantillons : 2,184678, 2,055871, 2,078289, 2,061179, 2,090475, 2,087641, 2,085472. Poste Windows, Docker, Node absent de l'hôte (image `node:20.20.2-bookworm` épinglée). La ligne T1.8 n'est pas réécrite. | Non : System Design §10. |
| 2026-11-10 | `CreateArtifactRecord` et `GetArtifactRecord` appliquent le schéma fermé ARTIFACT. `creator*`, `docType` et `txTimestamp` viennent du certificat et de l'horodatage de la transaction. Un champ de plus est `SCHEMA`, un doublon `DUPLICATE`, un rôle autre que `pipeline-agent` `FORBIDDEN`, une clé absente `NOT_FOUND`. L'existence du parent, le même `caseId` et « original sans parent » restent pour l06. | T2.5a (1/2), Schema §5.2, AC-07.3, NFR-03, IF-10. `NOT_FOUND` n'est pas un des quatre codes IF-10 ; la lecture d'une clé absente reprend le jeton déjà utilisé par la démo. | Non : le schéma et IF-10 ne changent pas. |

## Problèmes

| Date | Problème | Tâche | Statut |
|---|---|---|---|
| 2026-11-09 | Aucune tâche commencée ; M1 en retard de 12 jours ; plan sans marge | T1.3 à T6.5 | T1.3 vérifié le 2026-11-09 ; le retard M1 et l'absence de marge restent acceptés — D-18, I-30 |
| 2026-11-09 | Pas de `pyproject.toml` ni de Python 3.11 du dépôt. La suite L a tourné avec `py -3` (Python 3.14.7, pytest 9.1.1). | T1.3 | contourné pour cet incrément ; T1.1 devra fournir l'environnement Python 3.11 |
| 2026-11-09 | Audit de code (`audit/AUDIT_REPORT.md`) : 26 constats, aucun critique ni majeur ; scripts Fabric durcis (ports sur 127.0.0.1, `ca.env` en 0600, `status` sans effet de bord, interpréteur Python résolu) ; 7 corrections de specs en suite v2.1.1 | T1.3 | corrigé le 2026-11-09 ; décisions restantes dans « Trouvé, non construit » |
| 2026-11-09 | Node absent de l'hôte au départ (Node 22.17.0 est apparu pendant l'audit). `scripts/test-l.sh` type-vérifie les deux paquets avec le Node de l'hôte, sinon dans l'image `node:20.20.2-bookworm@sha256:…` du Compose (paquet monté en lecture seule, copié à part), sinon échoue (code 3) ; `SAAM_TEST_SKIP_NODE=1` ignore la vérification en le disant. Les avis sur `@grpc/grpc-js` et `protobufjs` sont levés (`fabric-shim` et `fabric-contract-api` en 2.5.8, `@grpc/grpc-js` 1.14.7, verrous régénérés, `npm audit` : 0). | T1.4 | corrigé le 2026-11-09 (audit passe 2, AUD-030, AUD-037) |
| 2026-11-09 | Audit de code, passe 2 (`audit/round-2/AUDIT_REPORT.md`) : 21 constats sur T1.4, 1 majeur, aucun critique. Majeur (AUD-046) : sous Linux les conteneurs (root) laissent des fichiers que l'utilisateur ne peut pas supprimer, donc `network.sh stop`/`start` échouent après le premier démarrage (DoD « levé/détruit 3 fois » rouge) ; trouvé en lançant la suite sur Ubuntu (WSL2), corrigé et revérifié là (8 passed). Autres corrections : bit exécutable des scripts, étiquette `saam.network` des conteneurs ponctuels, enrôlement et déploiement rejouables, paquets Fabric alignés, images Node épinglées, `python3` pour `test-l.sh`. | T1.3, T1.4 | corrigé le 2026-11-09 ; reste : test sur un hôte Linux natif (A-02.3), `test_check_ports_reports_a_busy_port` échoue sous WSL2 seulement (AUD-047) |
| 2026-11-10 | Audit de code, passe 3 (`audit/round-3/AUDIT_REPORT.md`) : 9 constats sur T1.8, aucun critique ni majeur. Corrigés : un échec de compilation faisait sortir `fabric/spike-latency.sh` avec le code 2, celui du dépassement de budget ; `npm run spike:latency` seul s'arrêtait faute de `BATCH_TIMEOUT` ; le test figeait `batchTimeout == "2s"` ; format ruff. Le script est testé sans réseau (19 tests, branches hôte et conteneur) ; branche conteneur vérifiée sur un réseau réel, sous Windows et sous Ubuntu/WSL2 (aucun fichier root restant). | T1.8 | corrigé le 2026-11-10 ; reste : test sur un hôte Linux natif (A-02.3) |
| 2026-11-10 | Audit de code, passe 4 (`audit/round-4/AUDIT_REPORT.md`) : 12 constats sur l04, aucun critique ni majeur, aucun défaut dans la logique du chaincode. Corrigés : la sonde de latence ne marchait qu'une fois par réseau (identifiants fixes, `CreateArtifactRecord` refuse les doublons) ; l'autorisation passait après la validation ; branches de sécurité sans test Jest ; tests compilés périmés jamais nettoyés (`dist-test`) ; `fabric/deploy-chaincode.sh` sans vérification des paquets et jamais appelé par l'enrôlement. Garde-fou de latence (AUD-068) : avec 7 échantillons le p95 est le plus lent, donc un hôte qui cale suffit à dépasser 7,3 s ; le test relance la sonde après un dépassement et n'échoue que si le dépassement se répète trois fois de suite (même budget à chaque exécution, ligne `LATENCY_RETRY` si un passage suit un dépassement) ; avant de passer `BatchTimeout` à 0,5 s, ne changer que si la médiane est aussi proche du délai. Avis `deepmerge` de Jest (AUD-063) : contournement par `overrides` sur 4.1.2 (aucune version corrigée n'existe), `npm audit` à 0, à retirer quand un correctif existe. | T2.5a | corrigé le 2026-11-10 ; reste : `@types/jest` à ajouter au TRD §18 et `NOT_FOUND` à IF-10 (AUD-064, AUD-065), `git switch -c l04-chaincode-create-get` avant le commit |
| 2026-11-10 | Le lecteur qui porte Node n'est pas monté : `node` et `npm` sont absents du PATH. La suite type-vérifie et lance Jest dans l'image épinglée. L'installation de Jest a signalé 6 avis npm de sévérité faible ; pas de `npm audit fix`. | T2.5a | contourné pour cet incrément |

| T2.10 | AC-16.1 passe (ondulation 0.3793 dB, attenuation 52.4227 dB >= 40 dB). NFR-21 mesure s?par?ment : RSB fixe/flottant global 55.8255 dB (< 60 dB), d?tails par ECG dans le bilan du 2026-11-16. Modifier coefficients/contrat prot?g? n?cessite une autorisation. |
| T2.10/T2.12 | Le g?n?rateur utilise maintenant `saam.hashing.artifact_hash`; l'identifiant inchang? `b6d7a73a` concorde avec l'API commune. R?g?n?ration r?p?t?e idempotente, JSON et paquet VHDL inchang?s entre deux g?n?rations. |

## Trouvé, non construit

| Date | Idée / besoin | Où | Proposé pour |
|---|---|---|---|

## Role I — T3.6 Ingestion Agent (2026-11-16)

### Implemented
- Created `saam/agents/ingestion.py` with WFDB and 12-lead CSV ingestion.
- Added ECG validation: dimensions, lead order, numeric values, finite samples and units.
- Removed WFDB header comments and replaced original record/data filenames.
- Restricted sanitized CSV output to the 12 expected ECG leads.
- Added report redaction for labeled patient names, identifiers, dates and supported name patterns.
- Added `saam/agents/redaction.py` and integrated report sanitization into ingestion.
- Sanitized artifacts are returned in memory; persistent storage and encryption remain backend responsibilities.
- Backend-generated `CASE-UUID` is accepted and validated; the ingestion agent does not generate another case ID.

### Privacy acceptance criteria
| Criterion | Current evidence | Status |
|---|---|---|
| AC-02.1 | WFDB metadata/header sanitization and CSV field restriction tested. Backend case-ID assignment is not implemented by this agent. | Partially verified |
| AC-02.2 | Test confirms two submissions can receive distinct backend-provided case IDs. Database-level absence of patient linkage is not verified. | Partially verified |
| AC-02.3 | Report redaction tests cover supported identity patterns and known names. Generic proper-name detection is not guaranteed. | Partially verified |

### Tests
- `tests/agents/test_ingestion.py` and `tests/agents/test_redaction.py` cover ingestion and privacy behavior.
- Agent tests: 21 passed.
- Full test suite: 133 passed, 1 skipped, 9 deselected.
- 11 warnings reported; no test failures.
- Full suite duration: 54.51 seconds.
- `git diff --check`: no whitespace errors; Git reports only an LF/CRLF conversion warning.

### Remaining work
- Integrate the ingestion agent with the backend worker after T3.5 is available.
- Verify backend-generated case IDs and database-level absence of patient linkage.
- Strengthen and validate proper-name detection in free-text reports.
- Verify the complete US-02 workflow, including the exact data stored by the backend.
- Mark US-02 done only after end-to-end acceptance tests pass.


## Role I ? T3.7 Preparation Agent (2026-11-16)

### Implemented
- Created `saam/agents/preparation.py` as a wrapper around `saam.dsp.prepare.prepare_ecg`.
- Generated `fir_input.npy`, `fir_stage.npy`, `signal.npy` and `processing_report.json` for successfully processed ECGs.
- Preserved NaN samples during ingestion so the preparation agent can assess signal quality.
- Rejected infinite samples and missing input files.
- Added per-lead quality reporting and rejection when quality is below the configured threshold.
- Added preparation tests covering valid signals, insufficient quality, invalid shapes and units.

### Validation
- Ingestion and preparation tests: 19 passed.
- Full test suite: previous result 139 passed, 1 skipped, 9 deselected.
- The full suite must be rerun after the latest missing-file test.

### Remaining limitations
- Manifest registration and artifact persistence are not yet integrated.
- Failure logging through the complete pipeline remains to be verified.
- T3.7 must not be considered fully integrated until these points are addressed.

## Role B — T3.1 Canonical hashing (2026-11-16)

### Implemented
- Added `saam/hashing` with the IF-05 API: `canonical_manifest`, `artifact_hash` and `file_hash`.
- Canonical manifests use the TRD §7.2 JCS (RFC 8785) serializer; floating-point values are rounded to six decimals and the top-level payload file list is sorted by name.
- File payloads are hashed as exact bytes with SHA-256. Invalid/non-canonicalizable manifests raise `ValueError`.
- Added hashing tests for canonical bytes, float rounding, file ordering, input immutability, 100 repeated artifact hashes, exact payload bytes and invalid inputs.

### Validation
- `.venv\Scripts\python.exe -m pytest tests/hashing -q`: 10 passed.
- `.venv\Scripts\ruff.exe check saam\hashing tests\hashing`: passed.
- `.venv\Scripts\mypy.exe --strict saam\hashing`: passed.
- `git diff --check`: passed.

### Remaining for acceptance
- The plan requires an inter-OS test in CI. No CI workflow exists in the checked-out project, and this increment did not implement T1.2; cross-OS verification remains pending. Therefore T3.1 is implemented and locally verified, but not yet fully accepted.
- Local checks used a temporary, ignored `.venv` with Python 3.13.2 because `uv`, Python 3.11 and the test dependencies were unavailable in the existing environment. No dependency or lockfile was added to the project in this increment.

## Role I — T3.8a CNN training and T3.8b fold-10 evaluation (2026-11-16)

### Data and training
- Verified PTB-XL v1.0.3 metadata checksums, official folds and all 21,799 `records500` WFDB pairs. Fold sizes: train 17,418 (folds 1–8), validation 2,183 (fold 9), test 2,198 (fold 10). No duplicate ECG IDs; each target superclass is represented in each split.
- Label audit over 21,799 records found 411 with no mapped diagnostic superclass and 5,144 with multiple mapped superclasses. Labels are multi-label as required.
- The previous 940,848,128-byte `.cache/ptbxl-prepared-v1/.signals.npy.incomplete` was not resumable: no labels, IDs or durable progress index existed. It remains untouched. The first new preparation also stopped at ECG 12722 (fold 2), whose lead V5 is constant zero and is rejected by production `prepare_ecg` during z-score normalization. Its partial cache remains at `ml/cache/ptbxl-prepared-t3.8a/`.
- The completed cache is `ml/cache/ptbxl-prepared-t3.8a-retry1/`: 19,601 records attempted, 19,600 prepared, and ECG 12722 explicitly excluded with the preparation error. This keeps training and inference on the same preparation contract.
- One CPU epoch completed with 17,417 training examples and 2,183 validation examples. Train BCE: 0.345053; validation BCE: 0.333861. On a fixed training batch, BCE fell from 0.702990 to 0.170680 over the epoch.
- Two repeated training runs on the same cache, seed 20261116, batch size 64 and CPU PyTorch produced identical model state tensors. RNG seeding now occurs after cache preparation, so worker-pool initialization cannot alter model initialization or batch order.
- Saved `ml/artifacts/ecg-cnn1d-1.0.0.pt` and `.json`. The checkpoint reload reproduced its probe prediction exactly. Config records the architecture (310,613 parameters), optimizer, learning rate, loss, class order, folds, seed, rejected ECG, package versions (Python 3.13.2, NumPy 2.5.5, PyTorch 2.15.0+cpu), losses and repeat-run determinism evidence.

### Fold-10 evaluation
- Added `ml/evaluate.py`; it evaluates only the untouched official fold 10 using the production preparation path, without adding a dependency.
- All 2,198 fold-10 records prepared successfully. Measured macro ROC AUC: 0.878077 (target ≥ 0.85 met); macro F1 at threshold 0.5: 0.648691. Per-class results and SHA-256 of the weights are in `ml/artifacts/model_card.json`.

### Verification and next dependencies
- `tests/ml tests/agents tests/dsp tests/hashing`: 73 passed. Ruff on changed ML files: passed. `mypy --strict saam/hashing`: passed. `git diff --check`: passed.
- Full suite with the repository-local Python path: 157 passed, 1 skipped, 9 deselected; one wrapper test failed because its nested `scripts/test-l.sh --board` pytest subprocess still uses the inaccessible global Windows temp directory (`PermissionError` on `C:\Users\ayedi\AppData\Local\Temp\pytest-of-ayedi`). No project test was disabled or weakened.
- T3.9–T3.12 are not yet implementable in dependency order: T3.9 requires T2.5b `RegisterModel`/`GetModel`, which is absent from the checked-out chaincode; T3.10 also requires the model registry; T3.11 and T3.12 depend on T3.10 and T3.11 respectively. These tasks remain pending rather than being stubbed around their real dependencies.


## Role I ? audit de reprise (2026-11-16)

### T1.6 ? PTB-XL
- `ml/data.py --check` passe sur PTB-XL v1.0.3 : 21 799 enregistrements, folds train/validation/test = 17 418/2 183/2 198, cinq classes pr?sentes par split.
- Sommes SHA-256 officielles v?rifi?es pour `ptbxl_database.csv`, `scp_statements.csv` et les 43 598 fichiers `.hea`/`.dat` de `records500` ; int?grit? valide. Les cinq vecteurs mat?riels du fold 10 ont aussi pass? `--check-hw-vectors`.
- Comptes de diagnostics affich?s : train CD 3 907, HYP 2 119, MI 4 379, NORM 7 596, STTC 4 087 ; validation 495/268/540/955/515 ; test 496/262/550/963/506.
- La voie de t?l?chargement atomique est impl?ment?e, mais non exerc?e puisqu'un dataset local valide ?tait d?j? disponible. La commande d'acceptation `--check` et la v?rification compl?te de l'int?grit? ont ?t? ex?cut?es.

### T2.10 ? FIR et NFR-21
- `hw/gen/gen_fir_coeffs.py` utilise `saam.hashing.artifact_hash`; l'identifiant reste `b6d7a73a`. Deux g?n?rations successives ont donn? les m?mes artefacts : JSON SHA-256 `7b0addfdfb6a947764306e226f027193f478b33a86bfa94cba8ca5a06a1614f8`, paquet VHDL `01c9b3481f815cb053e8a071589ca9e3f447c1d656f7c958d71185fb77aa647b`.
- R?ponse quantifi?e AC-16.1 conforme : ondulation 0.3793 dB et att?nuation de bande coup?e 52.4227 dB (minimum demand? 40 dB). NFR-21 mesure une autre grandeur : RSB de la sortie fixe par rapport au m?me filtre flottant = ECG 9: 55.6441, ECG 38: 55.1000, ECG 40: 56.3912, ECG 57: 55.7512, ECG 59: 56.1280 dB ; global 55.8255 dB (< 60). Tests DSP cibl?s : 29 pass?s. R?solution du d?ficit NFR-21 potentiellement li?e aux coefficients/au contrat arithm?tique prot?g?s ; laiss?e ouverte sans autorisation.

### T3.6 et T3.7 ? ?tat des crit?res
- T3.6 : les tests d'agent couvrent la suppression des m?tadonn?es WFDB, la production d'identifiants de cas distincts au niveau des soumissions et les motifs de d?tection/remplacement dans les rapports. L'int?gration ? la cr?ation de cas/backend n'est pas pr?sente ici ; AC-02.1/02.2 ne sont donc pas d?clar?s compl?tement v?rifi?s. La d?tection de nom propre s'appuie sur motifs/noms connus, sans NER g?n?rique ; la couverture exhaustive d'AC-02.3 reste non prouv?e.
- T3.7 : agent de pr?paration test? sur les sorties et le rapport de traitement, le seuil >10 % de valeurs invalides et le rejet d'entr?e illisible. Le passage du cas ? `rejet?` et la journalisation de bout en bout d?pendent de T3.5 absent ; AC-03.3 n'est pas enti?rement v?rifi? au niveau pipeline.

### T3.8a/T3.8b ? revue des crit?res officiels
- Le plan ?8 d?finit T3.8a par un entra?nement CPU, une ?poque et une baisse de perte ; une ?poque r?elle a baiss? la BCE d'un lot fixe de 0.702990 ? 0.170680. L'artefact final a ?t? recharg? et reproduit sa pr?diction de contr?le exactement.
- T3.8b ?value exclusivement le fold 10 ; macro ROC AUC r?elle 0.878077 (seuil officiel >=0.85), macro F1 ? seuil 0.5 = 0.648691. Entra?nement folds 1?8, validation fold 9, fold 10 en cache d'?valuation s?par?. Le r?glage n'a pas consult? le fold 10.
- Artefacts pr?sents : poids `.pt`, configuration `.json`, `model_card.json`, m?triques par classe et hash des poids. Une exclusion r?elle est document?e : ECG 12722 (fold 2, d?rivation V5 constante) rejet? par la pr?paration ; 17 417 exemples entra?nement et 2 183 validation. Deux r?p?titions ? graine 20261116 produisent des tenseurs de poids identiques. Les limites, versions et param?tres figurent dans la config/model card.
- Les crit?res du plan et les preuves locales ci-dessus concordent ; aucun r?sultat n'est estim? ou substitu?.

### Wrapper `scripts/test-l.sh --board`
- L'?chec n'est pas un ?chec de test fonctionnel : le pytest enfant re?oit `PermissionError` en cr?ant des r?pertoires sous `%LOCALAPPDATA%\Temp\pytest-of-ayedi`. La suite enfant a 117 pass?s, 1 ignor?, 9 d?s?lectionn?s et 41 erreurs d'acc?s au r?pertoire temporaire ; le wrapper agr?ge cela en un ?chec. Le parent avait 157 pass?s, 1 ignor?, 9 d?s?lectionn?s.
- L'essai `PYTEST_ADDOPTS=--basetemp=.cache/test-l-child-temp -p no:cacheprovider` n'a pas corrig? le chemin choisi par le pytest enfant. Aucun test n'a ?t? d?sactiv? ou modifi?. Il reste ? corriger la configuration d'environnement temporaire du wrapper pour les processus imbriqu?s Windows.

### D?pendances et port?e ind?pendante
- T3.9 d?pend de T3.8b et surtout de T2.5b `RegisterModel`/`GetModel`, absent du chaincode disponible ; T3.10 d?pend de T3.9, T3.11 de T3.10, T3.12 de T3.11. Aucun contournement/stub ajout?.
- T4.13 reste bloqu? par T4.12 et T3.22, absents (pas de client/coverify board, export et rapport requis). T5.4 est bloqu? par T3.17 et T4.1 ; `scripts/bench.py` absent. T5.9 est bloqu? par T4.8 et T4.1 ; scripts de requeue/reanchor et `tests/resilience/` absents. Aucun sous-ensemble autonome d?montrable identifi? dans ces t?ches.

### Validation de cette reprise
- `pytest tests/hashing tests/ml tests/dsp tests/agents -q`: 76 pass?s, 11 avertissements de d?pr?ciation ?mis par WFDB/pandas.
- Ruff sur `ml/data.py`, le g?n?rateur FIR et tests associ?s : OK. `mypy --strict saam/hashing` : OK. `git diff --check` : OK.
- Contr?le cibl?, pas de publication Git. Les caches et artefacts pr?c?demment produits restent en place.


## Role I ? exp?rimentation isol?e FIR ?chelle ?2 (2026-11-16)

- Aucun changement au g?n?rateur/coefficient FIR, ? `fir_coef_id`, au contrat `fir_fixed.py`, ? la pr?paration de production, au RTL, aux poids CNN ou aux caches PTB-XL existants.
- Conventions v?rifi?es : `fir_input` est `int16 = rint(mV ? 1000)` (unit? num?rique 1 ?V); l'?tage produit `int16` selon le contrat Q1.15 avec arrondi puis saturation. L'exp?rience double l'entr?e, conserve la sortie FIR en unit?s ?2 puis divise la sortie align?e par 2, en flottant, avant le passe-haut. La sortie filtr?e retrouve l'?chelle physique, avec l'erreur de quantification r?siduelle mesur?e ci-dessous.
- Outil isol? : `scripts/experiments/fir_scale_x2.py`; tests d?di?s dans `tests/dsp/test_fir_scale_experiment.py`. Rapports conserv?s sous `.cache/fir-scale-x2-*.json`; rapports canoniques : `fir-scale-x2-official-final-20261116.json` (5 vecteurs) et `fir-scale-x2-expanded-with-leads-20261116.json` + `fir-scale-x2-expanded-repeat-20261116.json` (55 ECG). Les deux rapports ?largis sont identiques octet pour octet. Les vecteurs officiels ont ?t? v?rifi?s contre les sources PTB-XL et sont ceux lus depuis `hw/vectors/ptbxl/`.
- Cinq vecteurs fold 10 : RSB global 55.825458 ? 61.812804 dB (sorties align?es : 55.872537 ? 61.859060 dB). Tous les 5 RSB agr?g?s par ECG d?passent 60 dB apr?s ?2. Les 60 d?rivations sont pr?sentes; le minimum individuel par d?rivation est 51.373611 dB (ECG 38, AVL), ce qui n'est pas le crit?re global de NFR-21.
- ?chantillon d?terministe r?parti sur folds 1?10 : 55/55 pr?par?s, aucun rejet; 5 par fold, avec 5 vecteurs officiels ajout?s au tirage fold 10. RSB global 57.694510 ? 63.717209 dB; sorties align?es ?2 : 63.762590 dB. Le minimum par ECG passe seulement de 50.346799 ? 56.373544 dB; le pire couple ECG/d?rivation apr?s ?2 est 47.277943 dB (ECG 9383, AVL). Le minimum agr?g? par d?rivation est 58.539971 dB. Le r?sultat global ne garantit donc pas les signaux faibles ni toutes les d?rivations.
- Aucun ?cr?tage d'entr?e/sortie dans les deux ?chantillons. Dans l'?chantillon large : maximum absolu d'entr?e 8 024 ? 16 048 apr?s ?2, sortie FIR max 15 330. La borne d'accumulateur calcul?e ? partir des ?chantillons ?2 est 1 001 026 096, sous la limite sign?e 40 bits 549 755 813 887. Le garde-fou exp?rimental rejette une entr?e 16 384, dont le double d?passerait int16.
- Compensation aval compar?e ? la sortie de pr?paration actuelle : sur les 55 ECG, RMSE du filtr? 0.358990 unit? num?rique (soit 0.000359 mV), ?cart absolu max 1.491466 unit?; pour l'entr?e normalis?e du CNN, RMSE 0.003435 et ?cart absolu max 0.045090. Aucun poids, cache ou score de classification n'a ?t? modifi? ou recalcul?.
- Les sondes NaN, hors plage de quantification et signal constant restent rejet?es par `prepare_ecg`; la politique qualit? n'a pas ?t? assouplie. Les tests d?di?s + DSP + agent preparation : 40 pass?s. Ruff et `git diff --check` passent.
- Conclusion exp?rimentale : ?2 d?passe le seuil RSB global sur les cinq vecteurs prescrits et dans l'?chantillon large agr?g?, mais ne garantit pas 60 dB aux faibles amplitudes/par d?rivation. L'int?gration changerait l'?chelle des artefacts `fir_input`/`fir_stage` et la convention de T2.12; aucun changement de production n'est propos? sans d?cision explicite. Le RTL source n'est pas pr?sent dans ce checkout, donc aucune co-simulation mat?rielle n'a ?t? possible.

## Role I - reprise T3.6/T3.7 (2026-11-16)

### T3.6 - ingestion et pseudonymisation (partielle)
- AC-02.1 : WFDB est reecrit avec un nom d'enregistrement pseudonymise, sans commentaires ni date/heure optionnelles d'en-tete; les fichiers CSV ne conservent que les 12 derivations autorisees. Les identifiants passes a l'agent doivent etre `CASE-<UUID>` canoniques; `new_case_id()` genere un UUID aleatoire. Tests couvrent l'en-tete, les metadonnees temporelles et les rapports stockes.
- AC-02.2 : deux generations locales fournissent des UUID distincts et aucun lien patient n'est conserve dans le resultat. L'unicite persistante/transactionnelle n'est pas prouvable sans creation de cas ni contrainte du backend; AC-02.2 reste partiel.
- AC-02.3 : les rapports remis a l'agent sont nettoyes avant leur ajout a `files` sous `report.txt`; les motifs et noms explicitement fournis sont couverts. La detection generique et exhaustive de tout nom propre n'est pas garantie par l'approche regex/liste de l'Architecture; AC-02.3 reste partiel pour les noms inconnus.
- Les erreurs de lecture exposees par les agents n'incluent plus le chemin source. Il n'existe pas dans ce checkout d'API/couche `cases` pour enregistrer les cas, ni de stockage/log pipeline pour prouver l'absence de PHI dans les journaux de bout en bout.

### T3.7 - preparation ECG (partielle)
- L'agent utilise toujours `saam.dsp.prepare.prepare_ecg` et la convention T2.12 inchangee (`int16 = sat(rint(mV * 1000))`); aucune echelle x2 ni modification des coefficients FIR. Les rapports gardent `fir_coef_id` et les parametres DSP.
- L'evaluation de qualite est alignee sur le reechantillonnage, la fenetre de 10 s et la plage int16 du DSP. Un score par derivation et le compte/la cause des echantillons invalides figurent dans le rapport. Au seuil par defaut de 0,90, >10 % invalides renvoie `quality_insufficient`; les entrees encore invalides ne sont jamais interpolees ni ecretees.
- Les resultats traites fournissent les trois tableaux `.npy` et `processing_report.json`. Le rejet agent renvoie « preparation impossible » sans exposer l'exception brute. En revanche, aucun manifeste/TraceabilityTool, stockage des fichiers, transition du statut du cas ou journal `agent_logs` n'existe dans ce checkout : le critere « 4 fichiers dans le manifeste » et la partie pipeline de AC-03.3 restent bloques par T3.5 et l'integration stockage/tracabilite.
- Les tests ajoutes couvrent le flux CSV ingestion vers preparation, les sorties agent, l'identifiant FIR, le seuil pour NaN et valeurs hors plage, le rejet sans fuite d'erreur, la serialisation JSON et l'en-tete WFDB date.

### Validation de reprise
- `pytest tests/agents tests/dsp -q`: 74 passed (14 avertissements de depreciation WFDB/pandas).
- Ruff sur les six fichiers modifies de T3.6/T3.7 : passe.
- `git diff --check`: passe.
- Mypy sur les trois modules concernes n'a pas pu conclure : stubs pandas/WFDB manquants et conflit de resolution de package `agents`/`saam.agents`; aucun resultat de typage positif n'est revendique. Le depot ne configure pas Mypy pour ces modules (regle stricte limitee a hashing/storage).
- Aucun test existant n'a ete supprime, ignore ou affaibli. Aucun artefact/cache/modele anterieur n'a ete supprime. T3.6 et T3.7 ne sont pas declarees terminees tant que les criteres backend/manifeste/journalisation et les limites de detection de noms restent non verifies.

## Role I - audit des taches restantes et reprise (2026-11-16)

### Statut explicite au checkpoint
- Terminees et verifiees (preuves dans les sections precedentes) : T1.6, T2.11, T2.12, T3.8a, T3.8b.
- Partielles : T2.10 (NFR-21 sous la cible et issue ouverte), T3.6 (creation/unicite backend et detection exhaustive des noms non prouvees), T3.7 (persistance/manifeste/journalisation pipeline absents).
- Bloquees par dependances : T3.9-T3.12 (T2.5b RegisterModel/GetModel et chainage), T4.13 (T4.12 et T3.22), T5.4 (T3.17 et T4.1, machine de demonstration), T5.9 (T4.8 et T4.1, services backend).


### T4.13 - co-verification sur carte et etape 9
- Criteres officiels : AC-17.3 (carte absente/non programmee -> message injoignable, code 2, aucun verdict identique), AC-17.4 et NFR-20 (recalcul sur carte de l'empreinte et du FIR d'une derivation; etape <=15 s). Livrables du plan : `hw/host/coverify.py --target board` et `hw/host/demo_step.py`.
- L'audit des fichiers confirme que `hw/host/` et ses outils ne sont pas presents. T4.13 depend explicitement de T4.12 (protocole UART/PS et client carte) et T3.22 (export et rapport de co-verification); la chaine amont inclut T3.17, T3.20/T3.21 et la carte/equipement du jalon. Aucun test carte ne peut etre valide ici. Pas de sous-partie autonome conforme identifiee; aucun stub de carte ajoute.

### T5.4 - banc de charge
- Criteres officiels : executer selon System Design section 14, 10 creations de cas, 20 verifications, 500 lectures par 5 clients et 5 etapes 9; consigner mesures comparees aux budgets DF-01 a DF-05 et ouvrir une decision si une cible manque.
- `scripts/bench.py` est absent. T5.4 depend de T3.17 et T4.1, et de la machine de demonstration (Q-03 reste ouverte dans `review.md`). Les API/pipeline correspondants sont absents. Un benchmark synthetique ne verifierait pas les NFR du systeme; aucune simulation ni metrique n'a ete inventee.

### T5.9 - resilience
- Criteres officiels : FM-01/04/05/06, messages App Flow, reprise apres retablissement, absence de double ancrage; livrables `tests/resilience/`, `scripts/reanchor.py`, `scripts/requeue.py`.
- Ces repertoires/scripts, worker, API de verification et scenario demo sont absents. Depend de T4.8 et T4.1 (et services T3.3/T3.5, T2.6, base et reseau Fabric). Chaque panne specifiee doit etre exercee contre les services reels; aucun composant autonome utile sans les services ne peut demontrer l'acceptation. Rien n'a ete simule.

### T2.10 - FIR / NFR-21
- Le plan exige AC-16.1/16.4, saturation testee, regeneration idempotente, et NFR-21 RSB >=60 dB ou mesure reelle avec issue documentee. Les coefficients restent ceux de 111 taps Q1.15 (`fir_coef_id=b6d7a73a`); AC-16.1 respecte l'ondulation 0.3793 dB et l'attenuation 52.4227 dB contre 40 dB minimum.
- Le RSB de reference des 5 vecteurs reste 55.825458 dB, sous NFR-21. L'experience ×2 reste separee et documentee (5 vecteurs: 61.812804 dB global; echantillon elargi de 55 ECG: 63.717209 dB global, avec minimum par ECG 56.373544 dB apres ×2). Ces resultats exploratoires ne valident pas NFR-21 pour le systeme; aucun coefficient, contrat, seuil ni chemin de production n'a ete change. La resolution technique de NFR-21 reste ouverte et necessiterait une decision avant tout changement protege.

### T3.6 / T3.7 - sous-parties independantes
- Les tests existants couvrent les sorties d'agent, la qualite, la pseudonymisation, le rapport nettoye et la convention FIR. Ajout de deux regressions de confidentialite : les erreurs de lecture CSV et WFDB ne revelent ni chemin ni nom source prive.
- Limites inchangées : creation transactionnelle/unicite backend pour AC-02.1/02.2; detection exhaustive des noms propres pour AC-02.3; persistence, manifeste/TraceabilityTool, statut de rejet et `agent_logs` pour T3.7/AC-03.3 dependent de T3.5 et des composants de stockage/traceabilite absents. Aucun service simule.

### Diagnostic wrapper Windows et validation
- Le wrapper lui-meme ne supprime pas les options de test; il efface deliberement `PYTEST_ADDOPTS` afin que les commandes de suite soient stables. L'echec historique vient du processus pytest imbrique (le test `test_board_flag_runs_no_board_tests...`) qui choisit `%LOCALAPPDATA%\\Temp\\pytest-of-ayedi`, non accessible dans le sandbox Windows. Une tentative de reproduction sans venv dans le `PATH` s'est arretee avant pytest (interpreteur introuvable dans Git Bash), ce n'etait pas un echec fonctionnel.
- Avec `TEMP`, `TMP` et `TMPDIR` pointant vers un dossier temporaire neuf et accessible sous `.cache`, et le venv ajoute au `PATH` herite par Git Bash, `pytest tests/scripts/test_test_l.py -q` a passe : 13 passed en 49.65 s. Le test du wrapper et du mode `--board` est reste actif; aucun test n'a ete desactive ou affaibli. Aucun changement de `scripts/test-l.sh` n'etait necessaire.
- Regresion apres les deux tests de confidentialite : `pytest tests/agents tests/dsp -q`: 76 passed, 14 avertissements WFDB/pandas. Ruff sur les modules/tests T3.6-T3.7 : passe; `git diff --check` : passe. Mypy ne conclut toujours pas pour ces modules (stubs pandas/WFDB absents et resolution double `agents`/`saam.agents`); la configuration stricte du depot ne cible que hashing/storage.
- Les caches de tests sont dans des dossiers `.cache` nouvellement crees pour cette execution; aucun cache, poids ou rapport anterieur n'a ete supprime ni remplace. Aucun changement de branche ou operation de publication Git.
