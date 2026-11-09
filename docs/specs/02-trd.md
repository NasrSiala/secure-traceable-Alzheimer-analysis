# SAAMSTIAHF — TRD

| Owner | Reviewers | Status | Version | Last updated | Suite version | PRD | Architecture | System Design |
|---|---|---|---|---|---|---|---|---|
| Équipe projet | Encadrant `[TBD: nom, Q-12]` | Approved (vision validée par l'encadrant, D-15) | 2.0.3 | 2026-11-09 | 2.1.3 | [01-prd.md](01-prd.md) | [03-architecture.md](03-architecture.md) | [05-system-design.md](05-system-design.md) |

Depuis la suite v2.0.0, ce document garde la technologie et les exigences (stack, plateformes, cibles NFR, conventions d'API publique, sécurité, environnements, coûts). La structure et les ADR sont dans l'Architecture ; la tenue en charge et les pannes dans le System Design.

## 1. Objet et périmètre

Couvre la v1 du prototype (soutenance le 2026-11-30) : backend API, pipeline agentique, modèle IA, stockage hors chaîne, réseau Hyperledger Fabric de test, chaincode, passerelle ledger, interface web, et le volet matériel VHDL (cœurs SHA-256 et FIR sur Zybo Z7-10, banc de co-vérification — Architecture §5.6). Ne couvre pas : production, multi-machines, données réelles de patients (PRD §7).

## 2. Traçabilité des exigences

| PRD | Approche technique | Section |
|---|---|---|
| F-01 Ingestion + pseudonymisation | `POST /api/v1/cases` multipart ; parseur WFDB/CSV ; suppression des champs identifiants ; `CASE-<uuid4>` | §8, §12, Architecture §5.3 |
| F-02 Préparation | Agent `preparation` : quantification int16 à 500 Hz, étage FIR passe-bas 40 Hz + décimation ×5 en virgule fixe (modèle bit-exact partagé avec le VHDL, ADR-14), passe-haut 0,5 Hz, normalisation z-score par dérivation, score de qualité | Architecture §5.3, §5.6 |
| F-03 Analyse IA | Agent `prediction` : CNN 1D PyTorch, 5 superclasses PTB-XL, sigmoïdes multi-étiquette (ADR-08) | Architecture §5.3, ADR-08 |
| F-04 Validation | Agent `validation` : règles R1–R5 configurables, re-vérification d'intégrité des ancêtres | Architecture §5.4 |
| F-05 Explication + résultat final | Agents `explanation` (gabarit) et `finalization` | Architecture §5.3 |
| F-06 Hachage | Manifeste canonique JCS + SHA-256 (ADR-04) | §7.2 |
| F-07 Stockage hors chaîne | Volume fichiers chiffrés AES-256-GCM (ADR-05) | §5, §12, ADR-05 |
| F-08 Ancrage Fabric | Chaincode TypeScript `provenance` ; service `ledger-gateway` (ADR-02) | §8.3, Architecture §5 |
| F-09 Orchestration agentique | LangGraph `StateGraph` dans le `worker`, file de jobs PostgreSQL (ADR-03) | §11, Architecture §5.2 |
| F-10 Historique | `GET /api/v1/cases/{id}/history` → chaincode `GetCaseHistory` | §8 |
| F-11 Vérification | Agent `verifier` : recalcul + comparaison on-chain, 4 statuts | Architecture §5.5 |
| F-12 Tableau de bord | React + Vite + TypeScript (ADR-07) | §4, ADR-07 |
| F-13 Auth et rôles | JWT + Argon2id + matrice de rôles ; identités Fabric par agent (ADR-09) | §9 |
| F-14 Kit de démo / tests | `scripts/demo.py`, `scripts/tamper.py`, suite `tests/integrity/` | §16 |
| F-15 Cohérence ECG↔rapport | Règle R3 : lexique FR/DE/EN → superclasses | Architecture §5.4 |
| F-16 Saillance (P1) | Non planifiée en v1 (D-17) ; approche prévue si reprise : Integrated Gradients (Captum) | Architecture §5.3 |
| F-17 Explication LLM (P2) | Nœud LangGraph optionnel derrière drapeau `LLM_EXPLANATION_ENABLED` | Architecture §5.3 |
| F-18 SHA-256 en VHDL | `sha256_core` itératif (1 ronde/cycle) + bourrage matériel, enveloppe AXI4-Lite, PL du Zynq XC7Z010 (ADR-12, ADR-13) | Architecture §5.6 |
| F-19 FIR en VHDL | `fir_decim` : 111 coefficients Q1.15, 1 MAC séquentiel, décimation ×5, arrondi + saturation int16 ; coefficients générés (ADR-14) | Architecture §5.6 |
| F-20 Co-vérification | Niveau 1 : cocotb + GHDL en CI contre les modèles Python ; niveau 2 : carte via UART (`hw/host/coverify.py`) ; rapports `hw/reports/` | Architecture §5.6, §16 |

## 3. Plateformes et support

- **Plateformes :** application web desktop.
- **Versions minimales :** Chrome/Edge ≥ 120, Firefox ≥ 120 ; largeur ≥ 1280 px (écran de démo). Responsive mobile hors périmètre.
- **Accessibilité :** WCAG 2.2 AA (NFR-09).
- **Matériel :** Digilent Zybo Z7-10, Zynq-7000 `xc7z010clg400-1` (D-12) ; AMD Vivado + Vitis 2023.x ou plus récent (déjà installés) ; liaison PC ↔ carte par le port USB-UART de la carte.

## 4. Frontend et hébergement

- React 18 + Vite + TypeScript, React Router, TanStack Query (requêtes + polling), Tailwind CSS, tracé ECG avec Plotly.js (`react-plotly.js`).
- Servi en statique par nginx (conteneur `frontend`), qui fait aussi reverse proxy de `/api` vers `api`.
- Hébergement : machine de démo locale, Docker Compose.

## 5. Backend et base de données

| Service | Techno | Rôle |
|---|---|---|
| `api` | Python 3.11, FastAPI, SQLAlchemy 2, Alembic | REST, auth, création de cas, lecture, déclenchement de vérification |
| `worker` | Python 3.11, LangGraph, PyTorch (CPU), SciPy, wfdb, neurokit2 | Exécute le graphe d'agents pour chaque job |
| `ledger-gateway` | Node 20, TypeScript, Fastify, `@hyperledger/fabric-gateway` | Soumet/évalue les transactions Fabric avec l'identité de l'agent appelant |
| `postgres` | PostgreSQL 16 | Métadonnées (cas, artefacts, journaux, vérifications, utilisateurs, config), file de jobs, checkpoints LangGraph |
| `artifact-store` | Volume Docker `/data/artifacts` | Fichiers chiffrés (AES-256-GCM) |
| Fabric test-network | Fabric 2.5 LTS (fabric-samples) | 1 orderer Raft, Org1 (plateforme) + Org2 (audit), 1 peer chacune, Fabric CA par org, canal `medtrace`, état LevelDB |
| `hw/` (hors Docker) | VHDL-2008 ; GHDL + cocotb ; Vivado/Vitis ; C bare-metal ; Python (pyserial) | Cœurs PL, application PS, banc de co-vérification côté PC — **jamais appelé par le pipeline** (D-11) |

Région : locale (aucun cloud).

## 6. Architecture (résumé)

Monolithe modulaire Python déployé en deux processus (`api`, `worker`), plus une passerelle Fabric en TypeScript, le chaincode `provenance`, l'interface React et le volet matériel (Zybo Z7-10, hors chemin critique). Composants (SVC-ID), frontières, interfaces internes (IF-ID), propriété des données, graphe d'agents, règles de validation, vérification et contrats matériels (cartes de registres AXI, protocole UART, contrat arithmétique FIR) : voir [03-architecture.md](03-architecture.md) §5–§8. Charge, flux critiques et modes de défaillance : voir [05-system-design.md](05-system-design.md).

## 7. Modèle de données

Détail et DDL : [04-backend-schema.md](04-backend-schema.md). Entités : E-users, E-cases, E-artifacts, E-artifact_files, E-jobs, E-agent_logs, E-verifications, E-verification_items, E-validation_configs, E-models, E-login_attempts ; on-chain : enregistrements `ARTIFACT` et `MODEL`.

### 7.1 Enregistrement on-chain `ARTIFACT` (clé `artifactId`, index composite `case~artifact`)

`docType`, `artifactId`, `caseId`, `artifactType` (`original|processed|features|prediction|validation|explanation|final_result`), `sha256`, `createdAt` (ISO 8601 UTC fourni par le client, `txTimestamp` ajouté par le chaincode), `softwareVersion`, `modelVersion` (nullable), `parentArtifactId` (nullable pour `original`), `offchainRef` (`artifact://<artifactId>`), `creatorMspId`, `creatorId` (sujet du certificat), `creatorAgent` (attribut de certificat `agent`) — les trois `creator*` sont extraits par le chaincode, jamais fournis par le client. Définition champ par champ : Schema §5.2 (fait foi).

### 7.2 Règle de hachage canonique (ADR-04)

- Chaque artefact = un **manifeste** JSON + 0..n fichiers de charge utile.
- Charge utile : octets exacts (CSV/WFDB pseudonymisés, NPY v1.0.0 `float32` little-endian C-order, JSON en JCS RFC 8785, texte UTF-8 NFC).
- Manifeste : `{artifact_id, case_id, type, parent_artifact_id, created_at, software_version, model_version, metadata{…}, files:[{name, media_type, size, sha256}] trié par name}` sérialisé en **JCS**.
- **Empreinte de l'artefact = SHA-256(JCS(manifeste))** ; elle couvre donc les fichiers via leurs empreintes.
- Les flottants dans les JSON sont arrondis à 6 décimales avant sérialisation (stabilité inter-plateformes, NFR-12).

- **Propriété :** `api` possède users, cases, verifications ; `worker` possède artifacts, agent_logs ; chaincode possède les enregistrements on-chain.
- **Cycle de vie :** cas conservés jusqu'à purge manuelle (`scripts/purge_case.py`, admin) ; les enregistrements on-chain sont immuables (empreintes seulement) — une purge rend les artefacts `manquant`, ce qui est attendu.
- **Migrations / seed :** Alembic ; seed : 1 admin, 1 operator, 1 auditor de démo, config de validation v1, modèle v1 enregistré.

## 8. Conception de l'API

- **Style :** REST JSON, préfixe `/api/v1`. Spécification OpenAPI générée par FastAPI.
- **Conventions :** erreurs `{"error": {"code": "...", "message": "...", "details": {}}}` ; pagination `?page&size` (size ≤ 50) ; dates ISO 8601 UTC ; création de cas idempotente via en-tête `Idempotency-Key` (optionnel).
- **Limites imposées :** `/auth/login` 10 req/min/IP ; `POST /cases` 10 req/min/utilisateur (slowapi).

### 8.1 Endpoints `api`

| Méthode | Chemin | Rôles | Story |
|---|---|---|---|
| POST | `/auth/login` | public | US-11 |
| POST | `/auth/refresh` | authentifié | US-11 |
| POST | `/auth/logout` | authentifié | US-11 |
| GET | `/me` | authentifié | US-11 |
| POST | `/cases` (multipart : `ecg_files[]`, `report_file` ou `report_text`, `csv_sampling_rate?`) | operator, admin | US-01, US-02 |
| GET | `/cases` | tous | US-09 |
| GET | `/cases/{case_id}` (statut, étapes, prédiction, validation, explication, résultat, empreintes, tx_id) | tous | US-04–US-07 |
| GET | `/cases/{case_id}/signal?artifact=processed` (tracé décimé) | tous | US-04 |
| GET | `/cases/{case_id}/history` (lu sur Fabric) | tous | US-09 |
| GET | `/cases/{case_id}/agent-logs` | tous | US-08 |
| POST | `/cases/{case_id}/verifications` | tous | US-10 |
| GET | `/cases/{case_id}/verifications` | tous | US-10 |
| GET/POST/PATCH | `/admin/users` | admin | US-11 |
| ~~GET/POST~~ | ~~`/admin/validation-configs`~~ — retiré v2.0.0 (D-17), remplacé par `scripts/registry.py config new\|activate` (IF-12) | admin | US-05 |
| ~~POST~~ | ~~`/admin/validation-configs/{id}/activate`~~ — retiré v2.0.0 (D-17) | admin | US-05 |
| ~~GET~~ | ~~`/admin/models`~~ — retiré v2.0.0 (D-17), remplacé par `scripts/registry.py model list\|activate` | admin | US-04 |
| ~~PATCH~~ | ~~`/admin/models/{id}`~~ — retiré v2.0.0 (D-17) | admin | US-04 |
| GET | `/health` (état de chaque service + version logicielle + modèle actif, pour S-12) | public | NFR-11 |

`scripts/registry.py` s'exécute sur la machine de démo avec le rôle de base `app_api` (le seul autorisé à écrire `validation_configs`, `schema.sql`) ; il applique les mêmes règles que les anciens endpoints : une nouvelle version de seuils est créée inactive, un modèle non ancré ne peut pas être activé. `scripts/register_model.py`, qui insère dans `models`, utilise le rôle `app_worker`.

### 8.2 Endpoints internes `ledger-gateway` (réseau Docker interne uniquement)

| Méthode | Chemin | Chaincode |
|---|---|---|
| POST | `/ledger/artifacts` | `CreateArtifactRecord` (submit) |
| GET | `/ledger/artifacts/{id}` | `GetArtifactRecord` (evaluate) |
| GET | `/ledger/cases/{caseId}` | `GetCaseHistory` (evaluate) |
| POST | `/ledger/models` | `RegisterModel` (submit) |
| GET | `/ledger/models/{name}/{version}` | `GetModel` (evaluate) |

### 8.3 Chaincode `provenance` (TypeScript, fabric-contract-api)

- `CreateArtifactRecord(json)` : valide le schéma ; refuse si la clé existe (AC-07.3) ; refuse si `parentArtifactId` non nul et inexistant ou appartenant à un autre `caseId` ; exige l'attribut de certificat `role=pipeline-agent` ; renseigne `creatorMspId`, `creatorId`, `txTimestamp` depuis le contexte ; émet l'événement `ArtifactAnchored`.
- `GetArtifactRecord(id)`, `GetCaseHistory(caseId)` (range sur la clé composite), `RegisterModel(json)` (attribut `role=model-admin`), `GetModel(name, version)`.
- Validation interne : `sha256` = 64 hex ; `artifactType` ∈ enum ; aucun champ hors schéma (refus de toute donnée libre → NFR-03).
- Politique d'endossement : `AND('Org1MSP.peer','Org2MSP.peer')` (D-07) — Org1 = plateforme, Org2 = audit.

## 9. Authentification et rôles

- **Connexion :** e-mail + mot de passe (Argon2id). Comptes créés par l'admin ; pas d'inscription publique.
- **Sessions :** JWT d'accès 30 min (en mémoire côté client) + jeton de rafraîchissement 8 h en cookie `HttpOnly; Secure; SameSite=Strict`, révoqué à la déconnexion. Verrouillage 15 min après 5 échecs en 15 min (AC-11.3). Codes : 401 identifiants invalides (message unique), 423 compte verrouillé, 403 compte désactivé, 429 limite de débit. Pas de MFA ni de réinitialisation par e-mail en v1 (l'admin réinitialise).
- **Services :** chaque agent a un jeton de service (secret partagé, en-tête `X-Agent-Token`) que `ledger-gateway` mappe vers l'identité Fabric correspondante (ADR-09).

| Role | Action | Allowed |
|---|---|---|
| operator | Créer un cas | Oui |
| operator | Consulter cas, historique, journaux | Oui |
| operator | Lancer une vérification | Oui |
| operator | Gérer utilisateurs / seuils / modèles | Non |
| auditor | Créer un cas | Non (403, AC-11.2) |
| auditor | Consulter cas, historique, journaux | Oui |
| auditor | Lancer une vérification | Oui |
| auditor | Gérer utilisateurs / seuils / modèles | Non |
| admin | Toutes les actions ci-dessus (utilisateurs via S-08 ; seuils et modèles via `scripts/registry.py`, D-17) | Oui |
| agent (identité Fabric `role=pipeline-agent`) | `CreateArtifactRecord` | Oui |
| verifier (identité Fabric, sans attribut) | Lectures chaincode | Oui ; écriture Non |
| admin (identité Fabric `role=model-admin`) | `RegisterModel` | Oui |

## 10. Services externes

| Provider | Purpose | Limits | Cost | SLA | Credentials owner | If slow/down | Exit plan |
|---|---|---|---|---|---|---|---|
| PhysioNet (PTB-XL v1.0.3) | Téléchargement du jeu de données (une fois) | — | Gratuit | Aucun | — | Copie locale + somme de contrôle dans le dépôt de données | Miroir local |
| Docker Hub (images Fabric, Postgres, Node, Python) | Images de base | Limites de pull anonymes `[TBD]` | Gratuit | Aucun | — | Images pré-tirées sur la machine de démo | `docker save` des images |
| AMD Vivado + Vitis (≥ 2023.1, déjà installés, D-12) | Synthèse, implémentation, bitstream, application PS | Licence gratuite couvrant le XC7Z010 `[TBD: confirmer l'édition installée]` | Gratuit | Aucun | Membre L | Un seul poste de build matériel ; bitstream et XSA archivés par release | Les cœurs restent simulables par GHDL sans Vivado |
| Digilent (fichiers de carte Zybo Z7-10, `vivado-boards`) | Préréglage du PS7 (DDR, MIO, horloges) | — | Gratuit | Aucun | — | Copie versionnée dans `hw/vivado/board_files/` `[TBD: licence]` | Configuration manuelle du PS7 |

Aucun service externe à l'exécution (démo hors ligne possible, carte démarrée depuis la carte SD).

## 11. Tâches de fond et événements

- File de jobs dans PostgreSQL (`E-jobs`) ; `worker` en boucle de polling 1 s ; 1 job à la fois (`WORKER_CONCURRENCY=1`).
- Réessai d'ancrage : 1 tentative initiale + 3 réessais (attentes 1 s/2 s/4 s), soit 4 tentatives au plus ; puis cas `erreur_ancrage` (AC-07.4).
- Job bloqué > 5 min sans heartbeat → remis en file, reprise par checkpoint LangGraph.
- Événement chaincode `ArtifactAnchored` : écouté par `ledger-gateway` pour journalisation (non bloquant).
- Aucune notification e-mail/push.

## 12. Sécurité et confidentialité

- **Données sensibles :** signaux ECG et rapports (même pseudonymisés) ; uniquement dans le stockage chiffré. PostgreSQL ne contient que métadonnées et résultats agrégés (classe, confiance, statuts).
- **Contrôles d'accès :** matrice §9, vérifiée dans une dépendance FastAPI par route + tests.
- **Chiffrement :** au repos, AES-256-GCM par fichier (nonce 96 bits aléatoire, AAD = `artifact_id|name`), clé maître `ARTIFACT_KEY` (32 octets) ; en transit, TLS sur nginx (certificat auto-signé de démo), TLS mutuel interne Fabric (test-network). Liaison `api`/`worker` ↔ `ledger-gateway` : réseau Docker interne + jeton.
- **Secrets :** fichier `.env` non versionné + `docker compose secrets` ; `.env.example` versionné ; wallet Fabric monté en lecture seule dans `ledger-gateway` uniquement.
- **Journal d'audit :** `E-agent_logs` (actions des agents), table `audit_events` côté API (connexions, création de cas, vérifications, actions admin) ; la chaîne elle-même sert de journal infalsifiable des ancrages.
- **Modèle de menaces :** (1) modification d'un fichier stocké → détectée (NFR-08) ; (2) modification de la base PostgreSQL (empreinte ou tx_id) → la vérification lit l'empreinte sur Fabric, pas en base ; (3) agent compromis réécrivant un enregistrement → refusé par le chaincode ; (4) fuite de PHI on-chain → schéma fermé + test automatisé ; (5) OWASP : injection (ORM paramétré), auth cassée (Argon2id, verrouillage), upload malveillant (taille, extension, parsing sans exécution, nom de fichier régénéré), CSRF (cookie SameSite=Strict + jeton en en-tête).
- **Volet matériel :** les exports de vecteurs (`hw/vectors/cases/`) contiennent des manifestes et des signaux PTB-XL pseudonymisés déchiffrés : produits uniquement par un admin (`ARTIFACT_KEY` requise), ignorés par git, supprimés après usage. La carte ne détient aucun secret ni aucune clé ; la liaison UART n'est pas authentifiée et reste locale (câble USB). Un résultat de la carte n'est jamais réinjecté dans le pipeline ni ancré.
- **Limite assumée :** un attaquant détenant la clé de chiffrement **et** capable de modifier le fichier produit quand même un artefact `modifié` (l'empreinte on-chain ne change pas). La blockchain ne prouve pas la justesse médicale (PRD §7).
- **Rétention :** voir §7.

## 13. Conformité

Prototype pédagogique sur données publiques PTB-XL (CC BY 4.0 : attribution dans le README et l'interface). Principes RGPD appliqués par conception (minimisation, pseudonymisation, rien d'identifiant on-chain car non effaçable) ; aucune certification (dispositif médical, HDS) visée.

## 14. Performance, montée en charge, fiabilité

| ID | Target | Value | Conditions |
|---|---|---|---|
| NFR-01 | Durée pipeline (création → résultat final ancré) | p95 ≤ 60 s | 1 cas à la fois, machine de démo `[TBD: specs, Q-03]`, CPU |
| NFR-02 | Vérification d'un cas (7 artefacts) | p95 ≤ 10 s | idem |
| NFR-15 | Réponse API de lecture (`GET /cases/{id}`) | p95 ≤ 300 ms | 5 utilisateurs simultanés |
| NFR-11 | Disponibilité | Pendant la démo uniquement ; `/health` vert pour tous les services | — |
| NFR-17 | Fermeture temporelle du design PL | WNS ≥ 0 à 100 MHz (FCLK_CLK0) | `xc7z010clg400-1`, après implémentation Vivado |
| NFR-18 | Ressources du design PL complet | ≤ 50 % des LUT, FF, BRAM et DSP du XC7Z010 `[cible à confirmer par T3.21]` | idem |
| NFR-20 | Durée de l'étape matérielle de démo (1 empreinte + 1 dérivation, aller-retour UART) | ≤ 15 s | 115 200 bauds |

- **Preuve de chaque cible :** System Design §2 (flux, estimation ou test).
- **Charge attendue :** < 100 cas au total, ≤ 5 utilisateurs simultanés (modèle de charge : System Design §3).
- **Montée en charge :** non visée ; `WORKER_CONCURRENCY` paramétrable.
- **Sauvegardes :** `pg_dump` + copie du volume artefacts + volumes Fabric avant la démo ; restauration testée en M5 (T5.7, au plus tard le 2026-11-25).
- **Reprise :** RPO = dernière sauvegarde manuelle ; RTO ≤ 30 min (re-création du réseau via script + restauration).

### Autres exigences non fonctionnelles

| ID | Exigence | Vérification |
|---|---|---|
| NFR-03 | Aucune donnée médicale brute ni identifiant direct on-chain | Schéma fermé du chaincode + test qui parcourt `GetCaseHistory` |
| NFR-04 | Artefacts chiffrés au repos | Test : fichier sur disque ≠ clair ; `file` ne reconnaît pas de format |
| NFR-05 | Accès authentifié et autorisé par rôle (utilisateurs et services) | Tests de la matrice §9 |
| NFR-06 | Chaque artefact (sauf `original`) référence son parent | Contrainte chaincode + FK en base |
| NFR-07 | Reproductibilité : versions modèle, logiciel (git SHA), config de validation, paramètres de préparation enregistrés dans les manifestes | Revue des manifestes |
| NFR-08 | Toute modification d'un artefact stocké est détectée | Suite `tests/integrity` |
| NFR-09 | WCAG 2.2 AA, statuts non codés par la seule couleur | Audit axe DevTools |
| NFR-10 | Interface en français | Revue |
| NFR-12 | Hachage déterministe (même artefact → même empreinte, 100 répétitions, 2 OS) | Test de stabilité |
| NFR-13 | Modularité : agents IA, validation, stockage, ledger remplaçables via interfaces (`ModelRunner`, `ArtifactStore`, `LedgerClient`) | Revue de code |
| NFR-14 | Toute action d'agent journalisée (agent, étape, entrée, sortie, durée, statut) | Test AC-08.3 |
| NFR-16 | Équivalence bit à bit logiciel ↔ matériel : 100 % des vecteurs identiques (SHA-256 et FIR), en simulation et sur carte | Rapports de co-vérification N1 et N2 (Architecture §5.6) |
| NFR-19 | Build matériel reproductible : bitstream, XSA et application PS régénérés par script (`hw/vivado/build.tcl`, Vitis en ligne de commande), sans étape manuelle dans l'interface graphique ; version Vivado consignée ; registre VERSION = SHA git | Rebuild depuis un clone propre en M5 (T5.8) |
| NFR-21 | Précision de l'étage FIR à virgule fixe : RSB ≥ 60 dB par rapport au même filtre en flottant, sur les 5 enregistrements `hw/vectors/ptbxl/` `[cible à confirmer par T2.10]` | Test `tests/dsp/test_fir_fixed.py` |

## 15. Observabilité

Logs JSON structurés (structlog / pino) avec `case_id` et `trace_id` sur tous les services ; `docker compose logs` suffit. Métriques : durées par étape dans `E-agent_logs` ; événements PRD §11 écrits dans `audit_events` (sauf `hw_coverification_completed`, écrit dans les rapports `hw/reports/`). Volet matériel : rapports d'utilisation et de timing Vivado archivés avec chaque bitstream. Pas d'alerting (prototype).

## 16. Stratégie de test

- **Unitaires :** pytest (préparation, règles de validation, canonisation/hachage, chiffrement), chaincode (Jest + `fabric-shim` mocks) ; couverture ≥ 70 % sur `pipeline/` et `hashing/`.
- **Intégration :** `docker compose` + test-network ; pipeline complet sur 5 enregistrements PTB-XL fixés (fold 10).
- **Intégrité (livrable CDC §12) :** `tests/integrity/` : tout valide ; 1 octet modifié dans un fichier chiffré ; fichier re-chiffré avec contenu altéré ; fichier supprimé ; enregistrement Fabric absent (artefact injecté en base seulement) ; Fabric arrêté → `non_vérifiable`.
- **Modèle :** `scripts/evaluate.py` sur fold 10 → AUC macro, F1 macro, enregistré dans `model_card.json`.
- **E2E :** Playwright sur le scénario de démo (PRD §8).
- **Architecture :** contrôles d'aptitude (Architecture §12) en CI : import-linter, propriété des tables, privilèges PostgreSQL, oracles des bancs cocotb.
- **Charge et résilience :** banc `scripts/bench.py` (NFR-01, NFR-02, NFR-15) et injection de pannes FM-01, FM-04, FM-05, FM-06 (System Design §14).
- **DSP :** `tests/dsp/` : gabarit du filtre sur les coefficients quantifiés (AC-16.1), RSB virgule fixe vs flottant (NFR-21), stabilité de `fir_coef_id`.
- **Matériel N1 (simulation) :** `hw/sim/` (cocotb + GHDL) : FIPS 180-4, 1 000 messages aléatoires dont longueurs limites, sha256_axi via cocotbext-axi ; FIR sur int16 aléatoires, extrêmes et 5 enregistrements PTB-XL, fir_axi. Exécuté en CI à chaque PR touchant `hw/` ou `saam/dsp/` ou `saam/hashing/` (AC-17.2).
- **Matériel N2 (carte) :** `hw/host/coverify.py --target board` sur un cas de démo ; manuel (carte requise), avant chaque jalon à partir de M4 et la veille de la soutenance.
- **Données de test :** PTB-XL uniquement. Responsable QA : `[TBD: membre]`.

## 17. Environnements et livraison

| Environment | Purpose | Data | Who can deploy |
|---|---|---|---|
| Development | Poste de chaque membre, `docker compose up` + test-network | Sous-ensemble PTB-XL | Chaque membre |
| Démo (« staging ») | Machine de soutenance | PTB-XL (public) | Responsable intégration |
| Production | Aucune | — | — |

- **CI/CD :** GitHub + GitHub Actions (D-06) — lint (ruff, mypy, eslint), tests unitaires Python/TS, build des images, job `hw-sim` (GHDL + cocotb, co-vérification N1) ; merge bloqué si rouge. Vivado n'est pas exécuté en CI (taille, licence) : build matériel sur le poste du membre L, bitstream + XSA + `BOOT.bin` + rapports publiés comme pièces jointes de release GitHub.
- **Config :** variables d'environnement (`.env`), un fichier par environnement, jamais versionné.
- **Release :** tags git SemVer `v0.y.z` pendant le développement, `v1.0.0` à la soutenance (règle de versions du CHANGELOG) ; images taguées par SHA ; rollback = tag précédent + restauration de sauvegarde.

## 18. Dépendances et bibliothèques

Python : fastapi, sqlalchemy, alembic, pydantic, argon2-cffi, pyjwt, slowapi, langgraph, langgraph-checkpoint-postgres, torch (CPU), numpy, scipy, wfdb, neurokit2, captum (non planifié en v1, D-17), cryptography, rfc8785, httpx, structlog ; outillage : import-linter (contrôles d'architecture). Node : fabric-contract-api, fabric-shim, @hyperledger/fabric-gateway, @grpc/grpc-js, fastify, pino. Front : react, react-router, @tanstack/react-query, tailwindcss, plotly.js. Matériel : GHDL (≥ 3.0, VHDL-2008, GPL-2.0, outil uniquement), cocotb (BSD-3), cocotbext-axi (MIT), pyserial (BSD-3), AMD Vivado/Vitis (propriétaire, édition gratuite), fichiers de carte Digilent `[TBD: licence]`. Licences : MIT/BSD/Apache-2.0 (Fabric Apache-2.0). Versions épinglées (`uv.lock`, `package-lock.json`) ; `pip-audit` et `npm audit` en CI.

## 19. Estimation des coûts

| Item | Au lancement / mois | À l'échelle cible / mois |
|---|---|---|
| Infrastructure | 0 € (machines personnelles) | N/A |
| Entraînement du modèle | 0 € (CPU local ou GPU gratuit type Colab `[TBD]`) | N/A |
| Carte Zybo Z7-10, carte micro-SD, câble micro-USB | 0 € (carte appartenant à l'équipe, D-14) | N/A |

## 20. Choix de stack (décisions détaillées dans l'Architecture §11)

| Choix | ADR |
|---|---|
| FastAPI pour l'API | ADR-01 |
| Passerelle Fabric en TypeScript (`@hyperledger/fabric-gateway`) | ADR-02 |
| LangGraph déterministe + file de jobs PostgreSQL | ADR-03 |
| Hachage : manifeste JCS + SHA-256 | ADR-04 |
| Stockage hors chaîne : fichiers chiffrés AES-256-GCM | ADR-05 |
| PostgreSQL 16 | ADR-06 |
| React + Vite + TypeScript | ADR-07 |
| CNN 1D PyTorch sur PTB-XL `records500` préparés | ADR-08 |
| Une identité Fabric par agent | ADR-09 |
| État Fabric LevelDB + clés composites | ADR-10 |
| Suivi de progression par polling | ADR-11 |
| VHDL-2008, GHDL + cocotb | ADR-12 |
| AXI4-Lite + application PS bare-metal + UART | ADR-13 |
| FIR 111 coefficients Q1.15 + décimation ×5, modèle bit-exact partagé | ADR-14 |
| Monolithe modulaire, propriété des tables par module | ADR-15 |
| Volet matériel hors du chemin critique | ADR-16 |

## 21. Hypothèses

- Machine de démo : ≥ 16 Go RAM, 4 cœurs, Docker Desktop/Engine `[TBD: Q-03]`.
- Règle R3 : rapport PTB-XL d'origine (champ `report`, majoritairement allemand) ou texte français saisi, lexique FR/DE/EN (D-08).
- Endossement par les 2 organisations acceptable en latence (≈ 2 s/tx, à mesurer) `[TBD: mesure T1.8]`.
- Un GPU n'est pas nécessaire pour l'entraînement (≈ 17 k enregistrements, entrée [12,1000] à 100 Hz après préparation depuis `records500`) `[TBD: mesure T3.8a]`.
- Une carte Zybo Z7-10 appartenant à l'équipe est disponible tout le projet et le jour de la soutenance (D-14) ; Vivado/Vitis ≥ 2023.1 est installé sur au moins un poste (D-12).
- L'UART de la carte et l'application PS tiennent 921 600 bauds ; sinon 115 200 bauds suffisent (NFR-20) `[à valider en T1.9]`.
- Le SHA-256 itératif tient 100 MHz sur le XC7Z010-1 `[à valider en T3.21]`.

## 22. Risques et mitigations

| Risk | Likelihood | Impact | Mitigation / spike needed |
|---|---|---|---|
| Mise en place test-network + CA attributs + gateway | Élevée | Élevé | Spike T1.3/T1.4 (M1) : transaction de bout en bout depuis `ledger-gateway` avant tout autre travail Fabric |
| 7 transactions × latence d'endossement > budget 60 s | Faible | Moyen | Mesure T1.8 ; si besoin, `BatchTimeout` orderer à 0,5 s (System Design §10) |
| Dérive de canonisation entre agents | Moyenne | Élevé | Une seule bibliothèque `hashing/` partagée + test NFR-12 |
| Checkpoint LangGraph + ré-exécution → double ancrage | Moyenne | Moyen | `artifact_id` généré avant l'ancrage et persisté ; le chaincode refuse le doublon, le worker traite « déjà existant avec même empreinte » comme succès |
| Lexique R3 peu fiable sur rapports allemands | Moyenne | Faible | Règle « non_applicable » par défaut ; limites documentées |
| Écart d'arrondi/saturation/ordre des octets entre VHDL et Python | Moyenne | Élevé | Contrat arithmétique écrit (Architecture §5.6) ; oracle unique ; tests aux valeurs extrêmes et longueurs limites dès la simulation |
| Fermeture temporelle du SHA-256 à 100 MHz | Faible | Moyen | Rapport de timing dès T3.21 ; repli : FCLK_CLK0 à 50 MHz (décision à consigner, NFR-17 ajustée) |
| Bring-up Zynq (PS7, UART, SD) plus long que prévu | Moyenne | Élevé | Spike T1.9 (M1) : « hello » UART + registre AXI lu depuis le PS |
| Versions Vivado différentes selon les postes | Moyenne | Moyen | Un seul poste de build matériel ; version consignée (NFR-19) |

## 23. Jalons techniques

Alignés sur le plan de livraison du PRD §15, recalé le 2026-10-23 (D-17) ; les identifiants M1–M6 sont ceux du plan d'implémentation.

| Milestone | What must be proven | Target date |
|---|---|---|
| Fondations (plan M1–M2) | Transaction `CreateArtifactRecord` via gateway avec identité d'agent ; API + DB + auth ; PTB-XL chargé ; hello UART + registre AXI sur la Zybo ; GHDL + cocotb en CI ; coefficients FIR et modèle bit-exact | 2026-11-03 |
| Pipeline IA (plan M3, 1re moitié) | Préparation + modèle AUC mesurée + validation R1–R5 sur 5 cas ; SHA-256 et FIR validés en simulation (N1) | 2026-11-10 |
| Traçabilité (plan M3–M4) | Graphe LangGraph complet ancrant 7 artefacts ; vérification 4 statuts ; co-vérification N2 sur carte | 2026-11-20 |
| Démo (plan M5–M6) | UI complète, kit de démo, tests E2E et intégrité verts, étape matérielle, rapport | 2026-11-30 |

## 24. Questions ouvertes

Voir [review.md](review.md).

## 25. Glossaire

| Term | Meaning |
|---|---|
| JCS | JSON Canonicalization Scheme (RFC 8785) |
| Manifeste | Description JSON canonique d'un artefact, base de son empreinte |
| MSP | Membership Service Provider (identités Fabric d'une organisation) |
| Endossement | Exécution/signature d'une transaction par les peers requis |
| test-network | Réseau Fabric de démonstration de `fabric-samples` |
| Superclasses PTB-XL | NORM (normal), MI (infarctus), STTC (anomalies ST/T), CD (troubles de conduction), HYP (hypertrophie) |
| AXI4-Lite | Bus mémoire simple d'ARM pour accéder aux registres d'un bloc de la logique programmable |
| Q1.15 | Format à virgule fixe signé sur 16 bits, 15 bits de fraction |
| WNS | Worst Negative Slack : marge temporelle la plus défavorable (≥ 0 = contraintes tenues) |
| FSBL / BOOT.bin | Chargeur de premier niveau du Zynq / image de démarrage (FSBL + bitstream + application) |
| cocotb | Bibliothèque Python pour écrire des bancs de test de simulation HDL |
| `fir_coef_id` | Identifiant court (8 hex) du jeu de coefficients FIR |

Les autres termes sont définis dans le glossaire du PRD.
