**Titre :** `l01-fabric-network: réseau Fabric de test isolé, suite test-l.sh et correctifs de l'audit`

**Base :** `main` · **Branche :** `l01-fabric-network`

## Incrément
`l01-fabric-network` — T1.3 — 1,0 j

## Contenu
- `fabric/network.sh start|status|stop` : 2 organisations (Org1 plateforme, Org2 audit), orderer Raft, 3 CA (Org1, Org2, orderer), 1 pair par organisation, canal `medtrace`, état LevelDB. Projet Docker isolé `saam-medtrace` (ports hôte 18050–18056, publiés sur `127.0.0.1`) : l'arrêt ne supprime que ses propres conteneurs, volumes et réseau.
- `scripts/test-l.sh` (`--fabric`, `--board`, `--dry-run`) et marqueurs pytest `fabric` et `board`.
- Plan de L (26 incréments), règle de livraison par incrément (D-19), PROGRESS à jour.
- Correctifs issus de l'audit de code (`audit/AUDIT_REPORT.md`) : suite de specs v2.1.3 (voir `docs/specs/CHANGELOG.md`), dont le moindre privilège des rôles de base dans `schema.sql` (tables, colonnes et contraintes inchangées) et la table des erreurs IF-09/IF-07.

## Couverture
- T1.3 : DoD « levé/détruit 3 fois de suite » (test automatisé). **Le test sur un second poste reste à faire avec un autre membre (A-02.3).**
- TRD §5, ADR-10, Architecture §10.
- NFR-03 / Secrets : aucun secret, wallet ni certificat versionné (test d'hygiène git, `ca.env` en 0600).
- Audit : AUD-002, 003, 004, 005, 006, 007, 008, 009, 010, 011, 012–016, 019, 017.

## Tests
- **Nouveaux :**
  - `tests/fabric/test_network.py` : `status` hors service renvoie « unhealthy » ; `status` sans effet de bord ; 3 cycles démarrer/arrêter sans résidu, canal `medtrace` joint par les 2 pairs, LevelDB, conteneurs d'autres projets intacts.
  - `tests/scripts/test_network_contract.py` : images épinglées, noms isolés, ports en boucle locale, liste de ports identique à celle de `network.sh`.
  - `tests/scripts/test_network_helpers.py` : interpréteur Python introuvable, port occupé, port libre, `ca.env` sans CR, permissions 0600 (POSIX seulement).
  - `tests/scripts/test_git_hygiene.py`, `tests/scripts/test_test_l.py` : secrets hors git, aide et codes de sortie de `test-l.sh`.
- **Régression :** `./scripts/test-l.sh` → 18 passed, 1 skipped ; `./scripts/test-l.sh --fabric` → 3 passed.
- **Mis à jour :** aucun test supprimé, ignoré ni affaibli. Lint (ruff) corrigé dans 3 fichiers de tests, sans changer une assertion.

## Preuves
- `./scripts/test-l.sh` : `18 passed, 1 skipped, 3 deselected` (le test de permissions POSIX est ignoré sous Windows).
- `./scripts/test-l.sh --fabric` : `3 passed` (réseau sain à chaque cycle ; aucun conteneur, volume, réseau ni dossier généré après l'arrêt).
- `ruff check`, `ruff format --check`, `mypy tests` : propres.
- `schema.sql` chargé sur PostgreSQL 16 : 0 erreur, 13 tables ; 23 contrôles de privilèges passent.
- Non vérifié : Linux, `shellcheck`, second poste.
- Constats restants et décisions : `audit/AUDIT_REPORT.md` §8 (notamment AUD-001 : `pyproject.toml` et CI relèvent de T1.1/T1.2).

## Dépend de
Rien. T1.1 (B) n'est pas fait : l01 crée seulement `fabric/`, `chaincode/provenance/`, `ledger-gateway/` et `hw/`. À relire par un autre membre (A-02.3) ; la table des erreurs IF-09/IF-07 est à confirmer par B avant T2.7.
