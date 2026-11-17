# CHANGELOG — Suite de specs SAAMSTIAHF

## Politique de versions (x.y.z)

S'applique à chaque document de la suite (colonne « Version » de l'en-tête), à la version de la suite (colonne « Suite version » = dernière entrée de ce fichier) et aux tags git du logiciel.

| Niveau | Quand | Exemples dans ce projet |
|---|---|---|
| **x — majeure** | Changement qui peut casser la compatibilité avec ce qui est construit ou planifié | Retrait ou redéfinition d'une fonctionnalité P0, d'un critère d'acceptation ou d'un ID déjà utilisé ; changement incompatible du schéma (`schema.sql`), d'une API, d'un contrat (règle de hachage ADR-04, coefficients FIR `fir_coef_id`, carte de registres AXI, protocole UART) ; restructuration de la suite |
| **y — mineure** | Ajout compatible avec l'existant | Nouvelle fonctionnalité, story, critère, écran, endpoint, tâche, NFR, ADR, section ou document |
| **z — correctif** | Correction d'erreur ou petite amélioration sans changement de sens | Incohérence mécanique, coquille, clarification, date, libellé, mise en forme |

Règles :
- Remettre à zéro les niveaux inférieurs : 1.2.3 → 2.0.0 (majeure) ; 1.2.3 → 1.3.0 (mineure) ; 1.2.3 → 1.2.4 (correctif).
- Un document modifié prend le niveau de sa propre modification ; un document non modifié garde sa version.
- La suite prend le niveau le plus élevé parmi les documents modifiés (un document en majeure → suite en majeure).
- Chaque entrée de ce fichier indique la version de chaque document modifié et liste les documents vérifiés non modifiés.
- Tags git du logiciel : `v0.y.z` pendant le développement, `v1.0.0` à la soutenance.
- Les versions écrites avant cette règle (1.0, 1.1, 2.0) se lisent 1.0.0, 1.1.0 et 2.0.0 ; elles ont été réécrites ainsi dans la v2.0.1.

## Suite v2.1.4 — 2026-11-09
**Change:** l'outillage Node/TypeScript est ajouté à la liste des dépendances du TRD §18 (audit de code, passe 2).  **Requested by:** utilisateur (L)  **Decision:** accord de l'utilisateur (L), 2026-11-09 ; à confirmer par B (T1.1, CI)  **From audit:** AUD-038

- TRD v2.0.4 : §18, outillage Node : `typescript`, `@types/node`, `reflect-metadata` (requis par les décorateurs de `fabric-contract-api`), `jest` et `eslint` (déjà cités par §16 et §17 pour les tests et le lint du chaincode, absents de la liste). Correctif : ces paquets découlent de la pile déjà choisie (Node 20, TypeScript, ADR-02) ; aucune bibliothèque d'exécution n'est ajoutée.
- Plan v2.1.4 : §1, version du TRD recalée. Version de suite dans les en-têtes de tous les documents, AGENTS.md, PROGRESS.md et `schema.sql` : 2.1.4. Autres documents inchangés sur le fond.

## Suite v2.1.3 — 2026-11-09
**Change:** table complète des erreurs de la passerelle ledger (IF-09) et du client (IF-07), issue de l'audit de code (AUD-011).  **Requested by:** utilisateur  **Decision:** accord de l'utilisateur (L), 2026-11-09 ; à confirmer par B (T2.7, `LedgerClient`)  **From audit:** AUD-011

- Architecture v1.0.2 : IF-09, `code` = code du chaincode ; 401 jeton, 403 `FORBIDDEN`, 404 absent, 409 `DUPLICATE`, 400 `SCHEMA`, 422 `PARENT_MISSING`, 502 Fabric injoignable. IF-07, exceptions ajoutées avec leur statut : `InvalidRecord` (400, 422), `LedgerForbidden` (401, 403) en plus de `LedgerUnavailable` (502), `DuplicateRecord` (409), `RecordNotFound` (404). Correctif : le 403 était déjà prévu par le plan de L (l08) ; aucun code n'est implémenté.
- Plan v2.1.3 : §1, versions recalées. Version de suite dans les en-têtes de tous les documents, AGENTS.md, PROGRESS.md et `schema.sql` : 2.1.3. Autres documents inchangés sur le fond.
- Pour l05, l06, l08 (passerelle, chaincode) et T2.7 : utiliser cette table.

## Suite v2.1.2 — 2026-11-09
**Change:** moindre privilège des rôles de base dans `schema.sql`, décidé après l'audit de code (`audit/AUDIT_REPORT.md`).  **Requested by:** utilisateur  **Decision:** accord de l'utilisateur, 2026-11-09  **From audit:** AUD-002, AUD-008, AUD-009

- Backend Schema v2.0.3 : `schema.sql`, section des privilèges seulement — `app_worker` ne lit plus `users`, `refresh_tokens`, `login_attempts` ; `UPDATE` par colonnes sur `validation_configs` (`is_active`) et sur `artifacts` (`anchor_status`, `anchor_attempts`, `tx_id`, `anchored_at`), conformément à Schema §5.1 et §10 ; `app_api` peut supprimer dans `login_attempts` (rétention 30 jours, Schema §16). Tables, colonnes, contraintes et index inchangés : traité en correctif car aucun consommateur n'existe encore et les règles écrites du Schema §10 et §16 sont désormais appliquées par la base. Vérifié sur PostgreSQL 16 : 23 contrôles de privilèges passent (`audit/tools/verify_schema_patch.sh`).
- Plan v2.1.2 : §1, versions recalées. Version de suite dans les en-têtes de tous les documents, AGENTS.md et PROGRESS.md : 2.1.2. Autres documents inchangés sur le fond.
- Pour T2.1 : la migration Alembic initiale doit reproduire ces privilèges (`tests/db/test_grants.py`, T1.11).

## Suite v2.1.1 — 2026-11-09
**Change:** correctifs issus de l'audit de code (`audit/AUDIT_REPORT.md`) : rôle de base de `registry.py`, références et versions périmées, commentaire d'en-tête de `schema.sql`.  **Requested by:** utilisateur (audit de code)  **Decision:** —  **From audit:** AUD-003, AUD-012 à AUD-016, AUD-019

- TRD v2.0.3 : §8.1, `scripts/registry.py` s'exécute avec le rôle `app_api` (le seul autorisé à écrire `validation_configs` dans `schema.sql`), `register_model.py` avec `app_worker` ; §2, préfixe `/api/v1` dans deux lignes.
- Plan v2.1.1 : §1, versions des documents sources recalées (TRD 2.0.3, Backend Schema 2.0.2, System Design 1.0.2, App Flow 2.0.2, review et aar 2.1.1) ; T1.9, renvoi à Architecture §5.6 ; Annexe A, T2.5b rattachée à US-04.
- System Design v1.0.2 : §9, le dixième cas en file « termine » (et non « démarre ») après ≈ 4,5 min.
- Backend Schema v2.0.2 : `schema.sql`, commentaire d'en-tête (chemin `04-backend-schema.md`, versions) ; DDL inchangé, rechargé sur PostgreSQL 16 (0 erreur, 13 tables).
- traceability.md : T2.5b rattachée à US-04 ; T3.16b, S-02, T3.13, T3.14, T2.1, T2.2, T5.2, T5.5, T5.6, T6.1, T6.2 et T6.4 ajoutés aux éléments justifiés.
- Version de suite dans les en-têtes de tous les documents, dans AGENTS.md et PROGRESS.md : 2.1.1. PRD, Architecture, App Flow, Design Brief et plan de L gardent leur version.
- Non appliqué (décision requise) : moindre privilège des rôles de base dans `schema.sql` (AUD-002, AUD-008, AUD-009, correctif prêt dans `audit/proposals/`), table des codes d'erreur IF-09 (AUD-011).
- Non affecté sur le fond (vérifié) : périmètre, exigences, DDL, contrats, tâches et dates du plan.

## Suite v2.1.0 — 2026-11-09
**Change:** plan d'implémentation dédié au rôle L, itératif et incrémental ; règle de livraison par incrément (tests, branche du nom de l'incrément, merge request vers `main`).  **Requested by:** Nasr Siala (L)  **Decision:** D-19

- Plan de L v1.0.0 (nouveau document, `08-implementation-plan-L.md`) : 26 incréments pour les 18 tâches de L et leur part de T6.2 et T6.3 (17,6 j), 4 itérations plus une clôture, règles de livraison, suite de tests L, dépendances externes, capacité.
- Plan v2.1.0 : §1 (lien vers le plan de L), §3, §4 (règle de livraison par incrément), §5 (commande `./scripts/test-l.sh`). Tâches, DoD et dates inchangés.
- AGENTS.md : section « Livraison par incrément », déroulement, convention de branche et de merge request, commande `test-l.sh`, dossier `tests/fabric/`.
- review.md : D-19 ; PROGRESS.md : lien vers le plan de L.
- Version de suite dans les en-têtes des huit documents et du plan de L : 2.1.0. PRD, TRD, Architecture, Backend Schema, System Design, App Flow et Design Brief gardent leur version.
- Non affecté sur le fond (vérifié) : périmètre, exigences, DDL, contrats, tâches du plan 08, traceability.md (mêmes T-ID).

## Suite v2.0.2 — 2026-11-09
**Change:** nom du membre L (A-01.1 partielle) ; AAR-02 ; décision D-18 (plan inchangé, risque de calendrier accepté) ; correction de 5 lignes de tableau mal rendues.  **Requested by:** Nasr Siala (L)  **Decision:** D-18  **From AAR:** A-01.1, AAR-02

- Plan v2.0.2 : §3, L = Nasr Siala ; §12, risque de calendrier (D-18) ; versions de review.md et aar.md au §1.
- TRD v2.0.2 : deux lignes de tableau (`|` dans du code) échappées, sans changement de sens (§8.1).
- App Flow v2.0.2 : trois lignes de tableau échappées de la même façon (§5, §10).
- aar.md : statuts des actions A-01.x, AAR-02 (6 actions).
- review.md : I-30 ajouté puis accepté (D-18), verdict « prêt, risque de calendrier accepté », Q-11 et Q-12 mises à jour, Q-15 ajoutée, D-18.
- PROGRESS.md : état au 2026-11-09 ; AGENTS.md, traceability.md, `schema.sql` : version de suite.
- Version de suite dans les en-têtes des huit documents : 2.0.2. PRD, Architecture, Backend Schema, System Design et Design Brief gardent leur version.
- Non affecté sur le fond (vérifié) : périmètre, exigences, DDL, contrats, tâches du plan. Les dates de M1 et M2 sont dépassées mais inchangées, conformément à D-18.

## Suite v2.0.1 — 2026-10-23
**Change:** adoption de la politique de versions x.y.z (correctif : aucun changement de contenu).  **Requested by:** utilisateur  **Decision:** —

- Toutes les versions réécrites au format x.y.z (1.0 → 1.0.0, 1.1 → 1.1.0, 2.0 → 2.0.0) dans les en-têtes, le texte, `schema.sql` et l'historique de ce fichier ; PTB-XL `v1.0.3` inchangé.
- PRD v2.0.1, TRD v2.0.1 (tags git SemVer, §17), Architecture v1.0.1, Backend Schema v2.0.1 (+ en-tête de `schema.sql`), System Design v1.0.1, App Flow v2.0.1, Design Brief v2.0.1, Plan v2.0.1 (dont tag `v1.0.0` en T6.4) : notation des versions uniquement.
- CHANGELOG : section « Politique de versions » ajoutée.
- review.md, traceability.md, aar.md, AGENTS.md (règle de versions ajoutée), PROGRESS.md : version de suite 2.0.1.
- Non affecté sur le fond (vérifié) : périmètre, exigences, DDL, contrats, plan de tâches.

## Suite v2.0.0 — 2026-10-23
**Change:** passage à la suite étendue à 8 documents (Architecture et System Design ajoutés, AAR obligatoires) ; recalage du plan après un démarrage tardif ; validation de la vision par l'encadrant.  **Requested by:** utilisateur  **Decision:** D-15, D-16, D-17  **From AAR:** A-01.3

- Fichiers renumérotés : `03-backend-schema.md` → `04-backend-schema.md`, `04-app-flow.md` → `06-app-flow.md`, `05-design-brief.md` → `07-design-brief.md`, `06-implementation-plan.md` → `08-implementation-plan.md` ; liens mis à jour.
- PRD v2.0.0 : statut Approved (D-15) ; soutenance 2026-11-30 (D-16) ; F-16/US-14 non planifiée (D-17) ; AC-01.1 précisée (I-19) ; admin des seuils et modèles en ligne de commande ; dates des indicateurs et du plan de livraison recalées ; risques sans libellés de semaines.
- TRD v2.0.0 : §6 et §20 réduits à un résumé + liens (I-20) ; endpoints `/admin/validation-configs*` et `/admin/models*` retirés au profit de `scripts/registry.py` (I-29) ; preuves NFR renvoyées au System Design ; tests d'architecture et de pannes ; import-linter ajouté aux dépendances ; jalons recalés.
- Architecture v1.0.0 (nouveau) : 18 composants SVC, 16 interfaces IF, propriété des données, règles de dépendance, ADR-01 à ADR-14 repris du TRD, ADR-15 (monolithe modulaire, propriété par module) et ADR-16 (matériel hors chemin critique), contrôles d'aptitude.
- Backend Schema v2.0.0 : propriétaires d'entités = composants SVC (I-21) ; autorisations admin via script ; DDL inchangé, ré-exécuté.
- System Design v1.0.0 (nouveau) : modèle de charge, capacité (≈ 392 ko/cas), flux DF-01 à DF-07 avec budgets (DF-01 ≈ 27 s pour 60 s), cohérence, files asynchrones, montée en charge, FM-01 à FM-20, reprise, tests de charge et de pannes.
- App Flow v2.0.0 : S-09, S-10 et J-09 retirés (D-17) ; spécification CLI `registry.py` ; correspondance FM → écrans (§18).
- Design Brief v2.0.0 : notes S-09/S-10 retirées ; saillance marquée non planifiée ; tests d'utilisabilité à 2 testeurs ; calendrier recalé.
- Plan v2.0.0 : documents sources à 8 ; recalage 23/10 → 30/11 (jalons chevauchants, portes M2 le 03/11 et M6 le 27/11) ; rôles rééquilibrés (I-24) ; T1.11 (contrôles d'architecture) et T5.9 (injection de pannes) ajoutées ; T4.10 retirée, T4.7 réduite au script ; checkpoints M4, M5 ajoutés ; AAR à chaque checkpoint ; Annexe B (NFR → tests) ; 75 tâches actives.
- traceability.md : colonnes Composants et Flux ; US-14 reportée.
- review.md : I-19 à I-29 corrigés ; Q-02, Q-10, Q-11, Q-12, Q-14 mis à jour ; D-15 à D-17.
- aar.md (nouveau) : gabarit + AAR-01 (démarrage tardif), 6 actions.
- AGENTS.md / PROGRESS.md : 8 documents, règle AAR, nouvelles commandes, références Architecture §5.6, jalon M1 recalé.
- Non affecté sur le fond (vérifié) : `schema.sql` (DDL), contrats matériels (contenu identique, déplacé), tokens et composants du Design Brief, présentation `docs/presentation/` (document historique validé, non modifié).

## Suite v1.1.0 — 2026-10-06
**Change:** ajout d'un volet VHDL (cœur SHA-256 + filtre FIR de l'ECG sur Zybo Z7-10, co-vérifiés avec le logiciel, étape de démo en direct).  **Requested by:** utilisateur  **Decision:** D-10 à D-14

- PRD v1.1.0 : ajout F-18, F-19, F-20 (P0) et US-15 (AC-15.1–15.4), US-16 (AC-16.1–16.4), US-17 (AC-17.1–17.4) ; AC-03.1 précisée (étage FIR bit-exact) ; indicateurs (co-vérification 100 %, démo 9/9) ; hors périmètre matériel ; contraintes, risques, plan de livraison, critères de lancement, glossaire.
- TRD v1.1.0 : nouveau §6.6 (architecture `hw/`, conventions VHDL, cœur SHA-256 et carte de registres, FIR 111 coefficients Q1.15 vérifié + contrat arithmétique + carte de registres, intégration Zynq, protocole UART, co-vérification N1/N2) ; préparation révisée (§6.3) ; ADR-08 révisé, ADR-12 à ADR-14 ; NFR-16 à NFR-21 ; services externes, sécurité, tests, CI `hw-sim`, dépendances, coûts, hypothèses, risques ; §23 réaligné (I-17).
- Backend Schema v1.1.0 : aucune table ni champ on-chain ajouté ; `processed` gagne `fir_input.npy` et `fir_stage.npy` (§5.3) ; règles des exports matériels (§14, §15) ; `schema.sql` : en-tête seulement (DDL inchangé).
- App Flow v1.1.0 : J-10 (co-vérification) et J-11 (étape 9) en CLI, spécification d'action CLI, textes « IDENTIQUE / DIFFÉRENT », export dans les actions sensibles ; aucun écran ajouté.
- Design Brief v1.1.0 : règles de la sortie console projetée (pas d'écran web).
- Plan v1.1.0 : rôles L (Ledger & matériel) et I (IA & DSP) ; spikes T1.9 (Zybo) et T1.10 (GHDL + cocotb en CI) ; tâches T2.10–T2.12, T3.18–T3.22, T4.12–T4.14, T5.8, T6.5 (74 tâches) ; T1.6, T3.7, T3.8a, T6.2, T6.3 ajustées ; repli matériel ; retour arrière matériel.
- AGENTS.md / PROGRESS.md : arborescence `hw/`, commandes matériel, conventions VHDL, nouveaux cas « s'arrêter et demander ».
- traceability.md : lignes US-15 à US-17, US-03 mise à jour ; review.md : I-13 à I-18 (corrigés), Q-13 (close), Q-14, D-10 à D-14.
- Non affecté sur le fond (vérifié) : DDL PostgreSQL, rôles et autorisations, écrans S-01 à S-12, tokens et composants du Design Brief.

## Suite v1.0.0 — 2026-10-05
**Change:** création de la suite à partir du cahier des charges « Projet 1 », revue de cohérence et décisions D-01 à D-09.  **Requested by:** utilisateur  **Decision:** D-01 à D-09

- PRD v1.0.0 : F-01 à F-17, US-01 à US-14 ; F-15/US-13 passée en P0 (D-01) ; périmètre confirmé (D-02) ; AC-01.2 clarifiée (I-05) ; cible AUC (D-09) ; source du rapport (D-08).
- TRD v1.0.0 : ADR-01 à ADR-11, NFR-01 à NFR-15 ; endpoints d'activation admin (I-01) ; champs on-chain alignés sur le Schema (I-02, I-03) ; politique de réessai (I-04) ; codes HTTP de connexion (I-06) ; `/health` (I-07) ; GitHub Actions (D-06) ; endossement AND (D-07).
- Backend Schema v1.0.0 + `schema.sql` : 13 tables PostgreSQL, enregistrements on-chain ARTIFACT/MODEL ; `anchor_attempts` 0–4 (I-04) ; `citext` remplacé par `text` en minuscules + index unique (portabilité) ; DDL exécuté sur PostgreSQL 16.2.
- App Flow v1.0.0 : S-01 à S-12, J-01 à J-09 ; endpoints S-09/S-10 (I-01, I-09).
- Design Brief v1.0.0 : tokens, composants C-*, 23 couples de contraste calculés (tous AA).
- Plan d'implémentation v1.0.0 : M1 à M6, 59 tâches ; `AGENTS.md` et `PROGRESS.md` générés.
- traceability.md, review.md : créés ; statut des stories `ready`.
