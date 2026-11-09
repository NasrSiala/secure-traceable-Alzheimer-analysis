# AGENTS.md — SAAMSTIAHF

Instructions pour tout agent de code (et tout membre de l'équipe) travaillant dans ce dépôt. Suite de specs v2.1.3 (8 documents).

## À lire avant toute tâche

1. Ce fichier et [PROGRESS.md](PROGRESS.md) (tâche courante, décisions, problèmes).
2. La tâche dans [docs/specs/08-implementation-plan.md](docs/specs/08-implementation-plan.md) §8 et chaque ID listé dans sa colonne « Entrées » (US-/AC-, NFR-, SVC-, IF-, ADR-, E-, DF-, FM-, S-, C-). Rôle L : l'incrément dans [docs/specs/08-implementation-plan-L.md](docs/specs/08-implementation-plan-L.md).
3. Les décisions de [docs/specs/review.md](docs/specs/review.md) — elles priment sur les documents.
4. Les actions ouvertes de [docs/specs/aar.md](docs/specs/aar.md).

Propriété des sujets : PRD = périmètre et critères d'acceptation ; TRD = stack, NFR, API publique, sécurité ; Architecture = composants (SVC), frontières, interfaces (IF), propriété des données, ADR, contrats matériels ; Schema + `schema.sql` = données et autorisations ; System Design = flux (DF), budgets de latence, modes de défaillance (FM) ; App Flow = écrans, états, messages ; Design Brief = tokens et composants.

## Projet en bref

Prototype pédagogique : ECG (PTB-XL) + rapport → pipeline d'agents LangGraph (ingestion, préparation, caractéristiques, prédiction, validation, explication, finalisation) → chaque artefact stocké chiffré hors chaîne, haché (SHA-256 du manifeste JCS) et ancré sur Hyperledger Fabric (chaincode TypeScript `provenance`) → vérification d'intégrité. Interface React en français. Volet matériel : cœurs VHDL SHA-256 et FIR (passe-bas + décimation ×5) sur Zybo Z7-10 (`xc7z010clg400-1`), co-vérifiés bit à bit contre le logiciel, **hors ligne** — le pipeline n'appelle jamais la carte (ADR-16). **Ce n'est pas un outil de diagnostic.** Soutenance le 2026-11-30.

## Arborescence

Placer le code dans le composant indiqué par l'Architecture §5 ; respecter les règles de dépendance de l'Architecture §6.

```
saam/            # Python : api, identity, cases, registry, pipeline (agents LangGraph), traceability, verification, audit, hashing, dsp (fir_fixed, prepare), ledger (client)
hw/              # rtl (VHDL-2008), gen (générateurs), sim (cocotb + GHDL), vivado (build.tcl), ps_app (Vitis C), host (coverify, demo_step, zybo_client), vectors, reports
chaincode/provenance/   # TypeScript, fabric-contract-api
ledger-gateway/  # TypeScript, Fastify + @hyperledger/fabric-gateway (seul détenteur des clés Fabric)
frontend/        # React + Vite + TS + Tailwind
fabric/          # scripts test-network, enrôlement des identités
ml/              # données PTB-XL, entraînement, évaluation
scripts/         # seed, register_model, registry, demo, tamper, purge_case, reanchor, requeue, export_hw_vectors, backup/restore, bench, test-l
tests/           # unit, api, agents, arch, db, fabric, integration, integrity, resilience, dsp, e2e
docs/specs/      # la suite de specs (8 documents + traceability, review, aar, CHANGELOG)
```

## Commandes

| Objet | Commande |
|---|---|
| Lint | `uv run ruff check . && uv run mypy saam` ; `npm run lint` (frontend, ledger-gateway, chaincode) |
| Contrôles d'architecture | `uv run lint-imports && uv run pytest tests/arch -q` |
| Tests Python | `uv run pytest -q` |
| Tests d'intégrité | `uv run pytest tests/integrity -q` |
| Injection de pannes | `uv run pytest tests/resilience -q` |
| Chaincode / gateway | `npm test` dans le dossier concerné |
| Réseau Fabric | `./fabric/network.sh up && ./fabric/deploy-chaincode.sh` |
| Pile | `docker compose up -d --build` puis `curl -k https://localhost/api/v1/health` |
| Démo | `uv run python scripts/demo.py --record 00001` |
| Suite de tests du rôle L | `./scripts/test-l.sh` (sans réseau ni carte) ; `--fabric` ; `--board` |
| Charge | `uv run python scripts/bench.py` |
| DSP (modèle bit-exact) | `uv run pytest tests/dsp -q` |
| Matériel — simulation | `make -C hw/sim` |
| Matériel — build (poste L) | `vivado -mode batch -source hw/vivado/build.tcl` |
| Matériel — carte | `uv run python hw/host/coverify.py --case CASE-… --target board` |

Une tâche n'est terminée que lorsque sa commande de vérification passe et que `PROGRESS.md` est mis à jour.

## Déroulement

1. Prendre le premier incrément débloqué (plan de rôle ; sinon la première tâche du plan 08). Un incrément à la fois.
2. Lire ses entrées. Ne construire que ce que l'incrément demande.
3. Créer les tests, lancer la vérification de l'incrément et les contrôles standard ; corriger jusqu'au vert.
4. Mettre à jour `PROGRESS.md` : fait, preuve, décisions, problèmes.
5. Livrer : commit, push, merge request (section suivante).

## Livraison par incrément

Un incrément est le plus petit lot testé et démontrable (1 jour au plus). Le plan de rôle le définit (L : `docs/specs/08-implementation-plan-L.md`). Pour une tâche du plan 08 sans plan de rôle, la tâche est l'incrément et son nom est `t<ID>-<slug>`. Le nom d'un incrément est un nom de branche valide.

Après chaque incrément, dans cet ordre. Aucun incrément n'est commité sans ses tests.

1. Créer les tests : (a) tests des nouvelles fonctions ; (b) tests de régression : relancer toute la suite du rôle (`./scripts/test-l.sh` pour L) et figer par un test chaque bug corrigé ou contrat touché ; (c) mettre à jour les anciens tests que l'incrément change légitimement. Ne jamais supprimer, ignorer ou affaiblir un test (cas « s'arrêter et demander »).
2. Lancer la suite complète du rôle et la vérification de l'incrément : tout vert.
3. Commit Conventional Commits : `<type>(<incrément>): <résumé> [<tâche>]`.
4. Push sur une branche qui porte exactement le nom de l'incrément : `git switch -c <incrément> origin/main` au début, `git push -u origin <incrément>` à la fin.
5. Créer la merge request vers `main` (pull request GitHub) : `gh pr create --base main --head <incrément>`. Le corps liste les tâches, les AC et NFR couverts, les tests nouveaux, de régression et mis à jour, et les preuves (modèle : plan de L §3).
6. Mettre à jour `PROGRESS.md`. Ne pas fusionner soi-même : un autre membre relit et la CI est verte.

L'incrément suivant part de `main` à jour. Si la merge request précédente n'est pas fusionnée et que l'incrément en dépend, partir de sa branche et l'écrire dans la merge request.

## Conventions

- Python 3.11, ruff, mypy strict sur `saam/hashing` et `saam/storage` ; TypeScript `strict: true`.
- Interface et messages en français, textes exacts de l'App Flow §10, §18 et §20.
- Tokens et noms de composants du Design Brief (`C-*`) ; aucune couleur codée en dur hors tokens.
- Toute empreinte passe par `saam/hashing` (jamais de `hashlib` ad hoc sur du JSON).
- Tout artefact passe par `TraceabilityTool.record` (stocker → hacher → ancrer) ; un module n'écrit que ses propres tables (Architecture §8, ADR-15).
- VHDL-2008, `ieee.numeric_std` uniquement, une horloge, `aresetn`, aucune primitive constructeur dans `hw/rtl/` ; fichiers générés (`fir_coeffs_pkg.vhd`, `fir_coeffs.json`) jamais édités à la main.
- Les bancs cocotb utilisent les oracles du pipeline (`saam/hashing`, `saam/dsp/fir_fixed.py`) — jamais une seconde implémentation de référence.
- Contrat arithmétique FIR, cartes de registres AXI et protocole UART : Architecture §5.6 (fait foi).
- Commits Conventional Commits ; une branche par incrément, au nom de l'incrément ; merge request relue par un autre membre (voir « Livraison par incrément »).
- Versions au format x.y.z (politique dans `docs/specs/CHANGELOG.md`) : toute modification d'un document de spec met à jour sa version (majeure si elle casse la compatibilité, mineure si elle ajoute, correctif sinon), sa date, la version de suite de tous les en-têtes et ajoute une entrée au CHANGELOG. Tags git du logiciel : `v0.y.z`, puis `v1.0.0` à la soutenance.

## Garde de périmètre

Ne construire que ce que la tâche et ses IDs demandent. Toute idée en plus → `PROGRESS.md` section « Trouvé, non construit ». Rien de la liste « Hors périmètre » du PRD §7, ni F-16 (saillance) et S-09/S-10 (coupés, D-17).

## S'arrêter et demander (ne pas trancher seul) si

- un critère d'acceptation paraît impossible ou contredit un autre document ;
- il faut modifier `docs/specs/schema.sql`, le schéma on-chain du chaincode ou la règle de hachage (ADR-04) ;
- il faut modifier le contrat arithmétique ou les coefficients FIR (`fir_coef_id`), une carte de registres AXI, le protocole UART, ou l'horloge cible du PL (Architecture §5.6, NFR-17) ;
- une règle de dépendance de l'Architecture §6 devrait être enfreinte, ou le pipeline semble devoir appeler la carte (interdit, D-11, ADR-16) ;
- une dépendance absente du TRD §18 semble nécessaire ;
- un test existant devrait être supprimé, ignoré ou affaibli ;
- une vérification échoue encore après 3 tentatives ;
- une action supprimerait des données, réécrirait l'historique git ou toucherait la machine de démo ;
- une donnée non publique ou identifiante pourrait entrer dans le système ou sur la chaîne.

## Checkpoint de jalon

- À chaque checkpoint de jalon, écrire l'AAR dans `docs/specs/aar.md` avant de demander l'approbation. Vérifier d'abord les actions ouvertes de l'AAR précédent.
- Le jalon n'est pas approuvé tant que son AAR manque.

## Secrets et données

- Jamais de secret dans git : `.env`, wallet Fabric, `ARTIFACT_KEY`, mots de passe de seed. Seul `.env.example` est versionné.
- Uniquement des données PTB-XL publiques. Rien d'identifiant ni aucun contenu médical sur la chaîne (NFR-03).
- `hw/vectors/cases/` (exports déchiffrés) n'est jamais versionné et est supprimé après usage ; seuls `hw/vectors/ptbxl/` (public, attribution CC BY 4.0) et les rapports sans échantillons sont versionnés.
