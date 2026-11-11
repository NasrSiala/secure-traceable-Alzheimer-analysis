# PROGRESS — SAAMSTIAHF

Suite de specs : v2.1.4 (2026-11-09). Mettre à jour à la fin de chaque tâche.

## Courant

- **Jalon :** M1 — échéance 2026-10-28 dépassée ; porte M2 du 2026-11-03 non approuvée. Plan conservé tel quel, risque de calendrier accepté (D-18).
- **Équipe :** L = Nasr Siala ; I, B, F à nommer (A-02.3).
- **Plan de L :** [docs/specs/08-implementation-plan-L.md](docs/specs/08-implementation-plan-L.md) ; `l01-fabric-network` et `l02-agent-identities` sont poussés (l02 part de la branche l01, dont la merge request n'est pas fusionnée).
- **État au 2026-11-09 :** `l02-agent-identities` (T1.4) est implémenté, audité (passes 1 et 2 : `audit/`, `audit/round-2/`), vérifié sur ce poste (Windows) et sur Ubuntu/WSL2, commité et poussé sur la branche du même nom. Les merge requests de l01 et de l02 restent à ouvrir sur GitHub (`gh` absent) ; la MR de l02 dépend de celle de l01 et doit l'écrire. Test sur un hôte Linux natif et sur un second poste : à faire avec un autre membre (A-02.3).
- **Tâche suivante :** T1.8 `l03-latency-baseline` (L), chemin critique de B (T2.7 → T3.3) ; en parallèle T1.1 (B), T1.6 (I), T1.7 (F) dès que leurs porteurs sont nommés.
- **Bloquants :** noms de I, B, F ; voir `docs/specs/review.md`.
- **Point hebdomadaire :** vendredi 13/11, 20/11, 27/11 — ce fichier à jour, y compris « rien fait » (A-02.5).

## Fait

| Tâche | Date | Preuve (commande / lien) |
|---|---|---|
| T1.3 `l01-fabric-network` | 2026-11-09 | `bash -n` sur les scripts ; `py -3 -m pytest -q -o addopts= -m "not fabric and not board" tests` : 12 passed ; `py -3 -m pytest -q -o addopts= -m fabric tests` : 2 passed (3 cycles start/stop, canal `medtrace`, les deux pairs, LevelDB) ; `scripts/test-l.sh` et `scripts/test-l.sh --fabric` : exit 0. Après l'audit du 2026-11-09 : `scripts/test-l.sh` 18 passed, 1 skipped (test de permissions POSIX, ignoré sous Windows) ; `scripts/test-l.sh --fabric` : 3 passed (dont `status` sans effet de bord). Conteneurs et volumes `saam-medtrace` absents après stop. `git ls-files` ne contient aucun `.pem`, `.key`, `.crt`, `_sk`, wallet ni `ca.env`. |
| T1.4 `l02-agent-identities` | 2026-11-09 | `bash -n` sur les scripts Fabric : exit 0. `tests/fabric/test_identities.py` marqué `fabric` : 1 passed. `scripts/test-l.sh` : 19 passed, 1 skipped. `scripts/test-l.sh --fabric` : même suite locale, puis 4 passed (identités, écriture `agent-ingestion`, refus `verifier`, cycles réseau). `git diff --check` : exit 0. `fabric/wallet` et `fabric/.runtime` absents après stop ; `git check-ignore` accepte `fabric/wallet/agent-ingestion/key.pem` ; `git ls-files` ne liste aucun wallet, `.pem`, `.key`, `.crt` ni `_sk`. Aucun conteneur, volume ni réseau `saam-medtrace` restant. Le projet Fabric voisin (`orderer.example.com`, `peer0.org1.example.com`, `peer0.org2.example.com`, réseau `fabric_test`, volumes `compose_*`) est inchangé. Après l'audit du 2026-11-09 (passe 2) : Windows, `scripts/test-l.sh` 51 passed, 1 skipped, puis `tsc --noEmit` des deux paquets (Node 22) ; `scripts/test-l.sh --fabric` : 8 passed en 538 s (identités avec second enrôlement, écriture `agent-ingestion`, refus `verifier`, arrêt avec conteneur ponctuel oublié, 3 cycles, vérification TypeScript dans l'image Node). Ubuntu 22.04 sous WSL2 (ext4, uid 1000, moteur Docker Desktop) : `pytest -m fabric` 8 passed, aucun fichier root restant ; 50 passed en local, 1 échec propre à WSL2 (`test_check_ports_reports_a_busy_port`, AUD-047). `npm audit` : 0 vulnérabilité dans les deux paquets. Aucun conteneur, volume, réseau ni `fabric/wallet` restant. |

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

## Problèmes

| Date | Problème | Tâche | Statut |
|---|---|---|---|
| 2026-11-09 | Aucune tâche commencée ; M1 en retard de 12 jours ; plan sans marge | T1.3 à T6.5 | T1.3 vérifié le 2026-11-09 ; le retard M1 et l'absence de marge restent acceptés — D-18, I-30 |
| 2026-11-09 | Pas de `pyproject.toml` ni de Python 3.11 du dépôt. La suite L a tourné avec `py -3` (Python 3.14.7, pytest 9.1.1). | T1.3 | contourné pour cet incrément ; T1.1 devra fournir l'environnement Python 3.11 |
| 2026-11-09 | Audit de code (`audit/AUDIT_REPORT.md`) : 26 constats, aucun critique ni majeur ; scripts Fabric durcis (ports sur 127.0.0.1, `ca.env` en 0600, `status` sans effet de bord, interpréteur Python résolu) ; 7 corrections de specs en suite v2.1.1 | T1.3 | corrigé le 2026-11-09 ; décisions restantes dans « Trouvé, non construit » |
| 2026-11-09 | Node absent de l'hôte au départ (Node 22.17.0 est apparu pendant l'audit). `scripts/test-l.sh` type-vérifie les deux paquets avec le Node de l'hôte, sinon dans l'image `node:20.20.2-bookworm@sha256:…` du Compose (paquet monté en lecture seule, copié à part), sinon échoue (code 3) ; `SAAM_TEST_SKIP_NODE=1` ignore la vérification en le disant. Les avis sur `@grpc/grpc-js` et `protobufjs` sont levés (`fabric-shim` et `fabric-contract-api` en 2.5.8, `@grpc/grpc-js` 1.14.7, verrous régénérés, `npm audit` : 0). | T1.4 | corrigé le 2026-11-09 (audit passe 2, AUD-030, AUD-037) |
| 2026-11-09 | Audit de code, passe 2 (`audit/round-2/AUDIT_REPORT.md`) : 21 constats sur T1.4, 1 majeur, aucun critique. Majeur (AUD-046) : sous Linux les conteneurs (root) laissent des fichiers que l'utilisateur ne peut pas supprimer, donc `network.sh stop`/`start` échouent après le premier démarrage (DoD « levé/détruit 3 fois » rouge) ; trouvé en lançant la suite sur Ubuntu (WSL2), corrigé et revérifié là (8 passed). Autres corrections : bit exécutable des scripts, étiquette `saam.network` des conteneurs ponctuels, enrôlement et déploiement rejouables, paquets Fabric alignés, images Node épinglées, `python3` pour `test-l.sh`. | T1.3, T1.4 | corrigé le 2026-11-09 ; reste : test sur un hôte Linux natif (A-02.3), `test_check_ports_reports_a_busy_port` échoue sous WSL2 seulement (AUD-047) |

## Trouvé, non construit

| Date | Idée / besoin | Où | Proposé pour |
|---|---|---|---|
