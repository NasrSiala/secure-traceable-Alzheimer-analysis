# PROGRESS — SAAMSTIAHF

Suite de specs : v2.1.3 (2026-11-09). Mettre à jour à la fin de chaque tâche.

## Courant

- **Jalon :** M1 — échéance 2026-10-28 dépassée ; porte M2 du 2026-11-03 non approuvée. Plan conservé tel quel, risque de calendrier accepté (D-18).
- **Équipe :** L = Nasr Siala ; I, B, F à nommer (A-02.3).
- **Plan de L :** [docs/specs/08-implementation-plan-L.md](docs/specs/08-implementation-plan-L.md) ; premier incrément `l01-fabric-network` (branche du même nom, merge request vers `main`).
- **État au 2026-11-09 :** `l01-fabric-network` (T1.3) est implémenté, audité (`audit/AUDIT_REPORT.md`) et vérifié localement. Branche `l01-fabric-network` commitée et poussée ; merge request à ouvrir sur GitHub (`gh` absent de ce poste). Test sur un second poste : à faire avec un autre membre (A-02.3).
- **Tâche suivante :** T1.4 (L), chemin critique de B (T2.7 → T3.3) ; en parallèle T1.1 (B), T1.6 (I), T1.7 (F) dès que leurs porteurs sont nommés.
- **Bloquants :** noms de I, B, F ; voir `docs/specs/review.md`.
- **Point hebdomadaire :** vendredi 13/11, 20/11, 27/11 — ce fichier à jour, y compris « rien fait » (A-02.5).

## Fait

| Tâche | Date | Preuve (commande / lien) |
|---|---|---|
| T1.3 `l01-fabric-network` | 2026-11-09 | `bash -n` sur les scripts ; `py -3 -m pytest -q -o addopts= -m "not fabric and not board" tests` : 12 passed ; `py -3 -m pytest -q -o addopts= -m fabric tests` : 2 passed (3 cycles start/stop, canal `medtrace`, les deux pairs, LevelDB) ; `scripts/test-l.sh` et `scripts/test-l.sh --fabric` : exit 0. Après l'audit du 2026-11-09 : `scripts/test-l.sh` 18 passed, 1 skipped (test de permissions POSIX, ignoré sous Windows) ; `scripts/test-l.sh --fabric` : 3 passed (dont `status` sans effet de bord). Conteneurs et volumes `saam-medtrace` absents après stop. `git ls-files` ne contient aucun `.pem`, `.key`, `.crt`, `_sk`, wallet ni `ca.env`. |

## Décisions (prises pendant le build)

| Date | Décision | Contexte | Reportée dans les specs ? |
|---|---|---|---|
| 2026-11-09 | D-18 : plan inchangé, aucune coupe, soutenance du 30/11 maintenue | Équipe à 0 tâche ; 64,5 j de tâches pour 64 j-personne au maximum | Oui : review.md, aar.md, Plan §12 |
| 2026-11-09 | Réseau de test isolé `saam-medtrace` (label `saam.network=medtrace`, ports hôte 18050–18056, LevelDB). Une CA d'orderer s'ajoute aux CA Org1 et Org2. `osnadmin` est lancé depuis `fabric-tools:2.5.16`. `core.yaml` du pair est extrait au démarrage dans `fabric/.runtime/` (gitignoré). | Des conteneurs Fabric d'un autre projet occupent déjà les noms et ports usuels. L'image orderer 2.5.16 n'a pas `osnadmin` ; le montage MSP masque le `core.yaml` de l'image pair. | Non : le canal, les deux organisations, Raft et LevelDB restent ceux des specs. |
| 2026-11-09 | Moindre privilège des rôles de base (`schema.sql`, suite v2.1.2) : `app_worker` sans lecture des comptes, `UPDATE` par colonnes sur `artifacts` et `validation_configs`, `DELETE` sur `login_attempts` pour `app_api` | Constats AUD-002, AUD-008, AUD-009 de l'audit ; accord de l'utilisateur | Oui : schema.sql, 04-backend-schema.md, CHANGELOG. T2.1 devra reproduire ces privilèges |
| 2026-11-09 | Table des erreurs de la passerelle (IF-09/IF-07) : 401 jeton, 403 `FORBIDDEN`, 404, 409 `DUPLICATE`, 400 `SCHEMA`, 422 `PARENT_MISSING`, 502 Fabric | Constat AUD-011 ; décidé par L (Nasr Siala) | Oui : Architecture §7, CHANGELOG v2.1.3. À confirmer par B avant T2.7 |

## Problèmes

| Date | Problème | Tâche | Statut |
|---|---|---|---|
| 2026-11-09 | Aucune tâche commencée ; M1 en retard de 12 jours ; plan sans marge | T1.3 à T6.5 | T1.3 vérifié le 2026-11-09 ; le retard M1 et l'absence de marge restent acceptés — D-18, I-30 |
| 2026-11-09 | Pas de `pyproject.toml` ni de Python 3.11 du dépôt. La suite L a tourné avec `py -3` (Python 3.14.7, pytest 9.1.1). | T1.3 | contourné pour cet incrément ; T1.1 devra fournir l'environnement Python 3.11 |
| 2026-11-09 | Audit de code (`audit/AUDIT_REPORT.md`) : 26 constats, aucun critique ni majeur ; scripts Fabric durcis (ports sur 127.0.0.1, `ca.env` en 0600, `status` sans effet de bord, interpréteur Python résolu) ; 7 corrections de specs en suite v2.1.1 | T1.3 | corrigé le 2026-11-09 ; décisions restantes dans « Trouvé, non construit » |

## Trouvé, non construit

| Date | Idée / besoin | Où | Proposé pour |
|---|---|---|---|
