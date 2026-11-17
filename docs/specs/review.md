# SAAMSTIAHF — Revue de cohérence, questions et décisions

Suite version : 2.1.4 — 2026-11-09 (règle de versions x.y.z, CHANGELOG ; contenu de la v2.0.0 : passage à la suite étendue à 8 documents ; plan recalé, D-15 à D-17). Les références de sections dans les lignes des versions 1.x (ex. « TRD §6.6 ») désignent la numérotation de l'époque ; depuis la v2.0.0, le contenu de l'ancien TRD §6 et §20 est dans l'Architecture §5 et §11.

## Verdict : prêt pour l'implémentation — avec un risque de calendrier accepté (D-18)

| Critère | État |
|---|---|
| Les 8 documents existent et passent leurs contrôles propres | ✓ (Architecture et System Design créés en v2.0.0) |
| Aucun problème bloquant ou majeur ouvert (mineurs listés et acceptés) | ✓ (30 problèmes : 29 corrigés ; I-30, majeur, accepté par l'utilisateur via D-18 — voir le risque ci-dessous) |
| Aucune question ouverte bloquant une tâche de M1 à M3 | ✓ (8 questions ouvertes, aucune ne bloque une tâche de M1 à M3 ; Q-11 en retard est suivie par l'action A-01.1, Q-12 par A-01.4) |
| Périmètre du PRD confirmé par l'utilisateur | ✓ D-02, D-10 ; validé tel quel par l'encadrant (D-15) |
| Matrice de traçabilité complète pour toutes les stories P0/P1, statut `ready` | ✓ (colonnes Composants et Flux ajoutées ; US-14 reportée, D-17) |
| Chaque NFR a une preuve dans le System Design et une tâche de test dans le plan | ✓ (System Design §2 ; Plan Annexe B) |
| DDL du schéma exécuté ; fichiers agents générés, règle AAR incluse | ✓ DDL inchangé, ré-exécuté le 2026-10-23 sur PostgreSQL 16.2 (0 erreur, 13 tables) ; `AGENTS.md` (section Checkpoint de jalon), `PROGRESS.md` |
| `aar.md` existe avec le gabarit | ✓ AAR-01 et AAR-02 écrits (actions A-02.1 à A-02.6 ouvertes) |
| Même version de suite sur tous les documents | ✓ 2.1.4 |

**Risque accepté (D-18) :** plan inchangé, 64,5 j de tâches pour 64 j-personne au maximum (5 j/semaine, 16 jours ouvrés du 2026-11-09 au 2026-11-30), sans marge : la moindre attente de dépendance ou absence fait manquer le 2026-11-30. Les coupes du plan §2 restent la seule soupape, sur décision de l'utilisateur. **À faire maintenant :** A-02.3 (noms de I, B, F) et T1.3 puis T1.4 (L), chemin critique de B. **Première tâche du plan :** T1.1 Monorepo (B), puis en parallèle T1.3 Spike Fabric (L), T1.6 PTB-XL (I), T1.7 Frontend (F) ; ensuite T1.9 Spike Zybo (L), T1.10 GHDL + cocotb (B), T1.11 contrôles d'architecture (B).

## Problèmes

| ID | Severity | Docs | Description | Proposed fix | Status |
|---|---|---|---|---|---|
| I-01 | major | TRD, App Flow, Schema | S-09/S-10 activent une config / un modèle, mais le TRD §8.1 n'avait aucun endpoint d'activation | Ajout de `POST /admin/validation-configs/{id}/activate` et `PATCH /admin/models/{id}` au TRD ; référence dans App Flow S-09/S-10 | fixed |
| I-02 | major | TRD, Schema | Enregistrement on-chain : `creatorAgent` et `docType` présents dans le Schema §5.2, absents du TRD §7.1 | TRD §7.1 aligné, renvoi au Schema (propriétaire des données) | fixed |
| I-03 | major | TRD, Schema | Le Schema exige un parent du **même cas** ; le chaincode décrit au TRD §8.3 ne vérifiait que l'existence | TRD §8.3 : refus si le parent appartient à un autre `caseId` | fixed |
| I-04 | major | PRD, TRD, Schema | « Réessayé 3 fois » (AC-07.4) vs « 3 tentatives » (TRD §11) vs `anchor_attempts` 0–3 : ambigu (3 ou 4 tentatives) | Le PRD fait foi : 1 tentative + 3 réessais = 4 au plus ; TRD §11 reformulé, `CHECK` passé à 0–4 dans `schema.sql` et le Schema §5.1 ; DDL ré-exécuté | fixed |
| I-05 | minor | PRD, Schema, App Flow | AC-01.2 : « fichier > 20 Mo » vs « téléversement total ≤ 20 Mo » et durée minimale de 10 s absente du PRD | Clarification d'AC-01.2 (total ECG + rapport, durée ≥ 10 s), sans changement de périmètre | fixed |
| I-06 | minor | TRD, App Flow | Codes HTTP de connexion (423 verrouillé, 403 désactivé) utilisés dans l'App Flow, absents du TRD | Ajoutés au TRD §9 | fixed |
| I-07 | minor | TRD, App Flow | S-12 affiche les versions via `/health`, que le TRD ne décrivait pas | TRD §8.1 : `/health` renvoie l'état des services, la version et le modèle actif | fixed |
| I-08 | minor | PRD, Schema | Terme « statut rejeté » (AC-03.3, AC-04.3) vs modèle `status` + `decision` | Correspondance documentée au Schema §6 (`termine` + `rejete`) | fixed |
| I-09 | minor | App Flow | Marqueur provisoire `[assumes D-pending I-03]` sur S-10 | Retiré après I-01 | fixed |
| I-10 | major | PRD | F-15 (cohérence ECG ↔ rapport) en P1 alors que le CDC §4.4 en fait une règle de validation | Passée en P0 (D-01) ; US-13 incluse dans les critères de lancement | fixed |
| I-11 | minor | PRD, TRD, Plan | Hypothèses en attente (Q-04, Q-05, Q-06, Q-08) | Résolues par D-06 à D-09, marqueurs retirés | fixed |
| I-12 | minor | Design Brief | Deux couples de contraste à faible marge : warning/warning-bg 4,51:1 et success/success-bg 4,57:1 | Conservés (conformes AA) ; consigne « ne pas éclaircir » ajoutée au DB §7 | fixed |
| I-13 | major | TRD, PRD | La préparation v1.0.0 (passe-bande Butterworth IIR + notch, en flottant) ne peut pas être comparée bit à bit à un filtre VHDL (US-16) | ADR-14 : étage FIR passe-bas + décimation à virgule fixe, contrat arithmétique écrit, modèle Python partagé pipeline/oracle ; passe-haut 0,5 Hz conservé en logiciel ; notch supprimé (couvert par la bande atténuée) ; AC-03.1 précisée. Conception vérifiée : 111 coefficients Q1.15 → 0,379 dB / 52,6 dB | fixed |
| I-14 | major | TRD, Plan | Le modèle était entraîné sur `records100` de PTB-XL alors que l'inférence passe désormais par la préparation FIR depuis 500 Hz → écart entraînement/inférence | ADR-08 révisé : entraînement sur `records500` passés par la même `prepare.py` ; T1.6, T2.12, T3.8a ajustés | fixed |
| I-15 | major | TRD, Schema | US-16 compare la carte à « l'étage correspondant » de `processed`, mais cet étage (et son entrée quantifiée) n'était pas stocké ; l'artefact `original` n'est pas toujours l'entrée int16 à 500 Hz (CSV, autres fe) | `fir_input.npy` et `fir_stage.npy` ajoutés à `processed` (Schema §5.3, TRD §6.3/§6.6) | fixed |
| I-16 | major | Plan | Charge : le banc côté PC dans S6 surchargeait B (≈ 6 j pour 4 j disponibles) | Export + cible simulation déplacés en M3 (T3.22, B a de la marge) ; cible carte + étape de démo confiées à I (T4.13) ; client UART avec l'application PS chez L (T4.12) | fixed |
| I-17 | minor | TRD, Plan | Jalons du TRD §23 numérotés M1–M4 alors que le plan utilise M1–M6 (incohérence de la v1.0.0) | TRD §23 renommé selon le PRD §15 avec correspondance vers les jalons du plan | fixed |
| I-18 | minor | TRD, Plan | Restes « 100 Hz » (T1.6, hypothèse TRD §21) après le passage à `records500` | Corrigés | fixed |
| I-19 | minor | PRD, Schema, Architecture | AC-01.1 créait le cas au statut `en_cours`, alors que l'état initial du Schema est `en_attente` (le job n'est pas encore pris) | Schema propriétaire des états : AC-01.1 précisée (`en_attente` puis `en_cours`) | fixed |
| I-20 | major | TRD, Architecture | Dans la suite à 8 documents, le TRD portait la structure (§6) et les ADR (§20) | Contenu déplacé dans l'Architecture §5 et §11 (IDs ADR inchangés) ; TRD §6 et §20 réduits à un résumé + liens | fixed |
| I-21 | major | Schema, Architecture | Plusieurs entités avaient deux « services propriétaires » (cases, jobs, models, audit_events écrits par `api` et `worker`) | Propriété par module, un seul propriétaire par table (ADR-15, Architecture §8) ; Schema §4 aligné ; test d'architecture T1.11 | fixed |
| I-22 | major | Plan, System Design | Aucune preuve des NFR de performance, aucun test de pannes, aucun AAR aux checkpoints | System Design (DF-01 à DF-07, FM-01 à FM-20) ; T5.9 injection de pannes ; Annexe B ; AAR dans chaque checkpoint | fixed |
| I-23 | major | Plan, PRD, TRD, Design Brief | Calendrier obsolète : M1 et M2 dépassés sans aucune tâche commencée | Recalage 23/10 → 30/11 (D-17) ; AAR-01 | fixed |
| I-24 | major | Plan | Charge du rôle B (21,9 j) supérieure à sa capacité (≈ 21 j) après recalage | T3.11, T3.12, T5.4 → I ; T4.5, T4.6 → F ; B à 19,1 j (Plan §11) | fixed |
| I-25 | minor | Plan, TRD, Schema, System Design | `reanchor.py`, `purge_case.py` et `requeue.py` cités sans tâche | Ajoutés à T5.7 et T5.9 | fixed |
| I-26 | minor | Plan | Pas de texte de checkpoint pour M4 et M5 | Ajoutés, avec AAR | fixed |
| I-27 | minor | Architecture | Le diagramme des composants montrait une flèche aller-retour pipeline ↔ cases (cycle apparent) | Une seule direction : SVC-pipeline → SVC-cases (IF-02, IF-03) | fixed |
| I-28 | minor | PRD, Schema, Design Brief | Restes de libellés de semaines (S1–S8, « semaine 7 ») après recalage | Remplacés par jalons et dates | fixed |
| I-29 | minor | TRD, App Flow, Design Brief | Endpoints et écrans d'administration des seuils et modèles conservés après la coupe D-17 | Endpoints barrés ; S-09/S-10 retirés ; `scripts/registry.py` (T4.7) | fixed |
| I-30 | major | Plan, PRD, System Design | Jalons M1 (2026-10-28) et M2 (porte 2026-11-03) manqués, 0 tâche sur 18 commencée pour L (AAR-02) ; capacité de L du 09/11 au 30/11 ≈ 13 j pour 17,6 j de tâches, sans compter les attentes de dépendance ; dates du plan §7, §11 et PRD §15 périmées | Décision de l'utilisateur sur les coupes ou la redistribution (D-18), puis plan mis à jour, puis AAR | accepted — D-18 (2026-11-09) |

**Contrôles v1.1.0 (volet VHDL) passés sans écart :** F-18–F-20 couvertes dans les 6 documents (TRD §2/§6.6, Schema §5.3/§14, App Flow J-10/J-11 + spécification CLI, Design Brief sortie console, Plan T1.9–T6.5) ; gabarit FIR identique entre AC-16.1 et TRD §6.6 ; 1 011 sorties / 5 000 + 55 entrées cohérentes partout ; NFR-20 (15 s) identique entre TRD, App Flow et Plan ; aucun appel du pipeline vers la carte (D-11) dans le TRD, l'App Flow ou le Plan ; nouvelles dépendances listées au TRD §18 ; dépendances des tâches dans un ordre valide.

**Contrôles v1.0.0 passés sans écart :** couverture des stories (toutes les P0/P1 ont écran, entités, API, tâches) ; identifiants S-/C- identiques entre l'App Flow et le Design Brief ; rôles identiques dans PRD §3, TRD §9, Schema §10 et App Flow §2 ; plateforme web desktop partout ; enums de statut alignés entre Schema §6 et App Flow §10/§12 ; seuils (0,70 / 0,90, 20 Mo, 60 s, 10 s, 5 échecs/15 min) identiques partout ; rien du PRD §7 construit en aval ; P0 avant P1 dans le plan, seule la P1 est coupable ; composants compatibles avec React/Tailwind ; DDL conforme à PostgreSQL 16.

## Questions

| ID | Question | Why it matters | Options | Recommended | Blocks | Status |
|---|---|---|---|---|---|---|
| Q-01 | Confirmer le périmètre P0/P1/P2 | Base de toute la cascade | Confirmer / ajuster | Confirmer | Tout | closed (D-02) |
| Q-02 | Format attendu du rapport et du diaporama (la date de soutenance est fixée : 2026-11-30, D-16) | Livrables M6 | — | Demander à l'encadrant avec A-01.4 | T6.2 (M6) | open — propriétaire : équipe, échéance 2026-10-27 |
| Q-03 | Caractéristiques de la machine de démo | Conditions de NFR-01/02 ; Fabric + PyTorch en même temps | Portable d'un membre / machine du labo | Portable ≥ 16 Go de RAM d'un membre, figé en M4 | T5.4, T6.1 (M5–M6) | open — propriétaire : L, échéance 2026-11-09 |
| Q-04 | Cible d'AUC du modèle | Indicateur de succès du PRD | 0,85 / 0,80 / aucune | 0,85 | T3.8b | closed (D-09) |
| Q-05 | Hébergement du dépôt et CI | T1.2 en semaine 1 | GitHub / GitLab / pas de CI | GitHub + Actions | T1.2 | closed (D-06) |
| Q-06 | Texte du rapport pour R3 | US-13 en P0 | PTB-XL + FR saisi / FR seul / traduit | PTB-XL + FR saisi | T3.11 | closed (D-08) |
| Q-07 | Gestion de la clé `ARTIFACT_KEY` | Sécurité du stockage hors chaîne | `.env` + secret Docker / KMS local (Vault) | `.env` + secret Docker (prototype) ; `ArtifactStore` reçoit la clé par injection, donc remplaçable | — (non bloquant : l'interface ne change pas) | open — hypothèse de travail = recommandation ; propriétaire : L, échéance 2026-10-26 |
| Q-08 | Politique d'endossement | Force de la preuve multi-organisation | AND(Org1,Org2) / Org1 seule | AND(Org1,Org2) | T2.5a | closed (D-07) |
| Q-09 | Purge des données après la soutenance | Rétention (Schema §16) | Purge immédiate / conserver pour le rapport | Conserver jusqu'à la note finale, puis purge + destruction du réseau | — | open — propriétaire : équipe, échéance 2026-11-30 |
| Q-10 | Outil de maquette (Figma ou code direct) et logo dessiné | Organisation du travail front | Figma / code + Storybook | Code direct + Storybook optionnel (gain de temps) ; logotype texte suffisant | — (non bloquant) | open (en retard) — propriétaire : F, échéance reportée au 2026-10-28 (M1) |
| Q-11 | Noms des 4 membres et attribution des rôles L/I/B/F | Responsables des tâches | — | Attribution avant la première tâche | — (tâches attribuées par rôle ; cause de l'AAR-01) | partiellement close : L = Nasr Siala (2026-11-09) ; I, B, F à nommer — escaladée (A-01.1 ouverte à AAR-01 et AAR-02), action A-02.3, échéance 2026-11-10 |
| Q-12 | Nom de l'encadrant et dates des portes humaines recalées (M2 le 2026-11-03, M6 le 2026-11-27) | Approbations | — | Proposer ces dates à l'encadrant | Porte M2 (pas une tâche) | open (en retard, escaladée) — action A-02.4 (reprend A-01.4), échéance 2026-11-11 |
| Q-13 | Disponibilité de la carte Zybo Z7-10 | Spike T1.9 en S1, étape 9 en soutenance | Équipe / labo / plus tard | — | T1.9 | closed (D-14) |
| Q-14 | Édition et licence de Vivado installée (couvre-t-elle le XC7Z010 ?) ; licence des fichiers de carte Digilent | Build matériel, redistribution des fichiers de carte | Édition gratuite / sous licence | Vérifier dans Vivado (`Help › Manage License`) et dans le dépôt Digilent | — (non bloquant : vérifié dès T1.9 ; le XC7Z010 est un composant d'entrée de gamme) | open (en retard) — propriétaire : L, échéance reportée au 2026-11-12 (T1.9) |
| Q-15 | La porte encadrant M2 du 2026-11-03 a-t-elle eu lieu ? Quelle a été la réponse ? | Approbation du recalage et des coupes | — | L'équipe le dit à l'ouverture de A-02.1 | Plan §7 (pas une tâche) | open — propriétaire : Nasr Siala, échéance 2026-11-11 |

## Décisions

| ID | Answers | Decision | Decided by | Date | Docs updated |
|---|---|---|---|---|---|
| D-01 | I-10 | F-15 / US-13 (cohérence ECG ↔ rapport) passe en **P0** | Utilisateur | 2026-10-05 | PRD |
| D-02 | Q-01 | Périmètre confirmé : P0 = F-01…F-15, P1 = F-16, P2 = F-17 | Utilisateur | 2026-10-05 | PRD, toute la suite |
| D-03 | — | Documents rédigés en **français** | Utilisateur | 2026-10-05 | Tous |
| D-04 | — | Contraintes : **8 semaines, 4 personnes** | Utilisateur | 2026-10-05 | PRD §12, Plan |
| D-05 | — | Orchestration **LangGraph** ; données **PTB-XL** ; chaincode **TypeScript** | Utilisateur | 2026-10-05 | PRD §12, TRD (ADR-02, ADR-03, ADR-08) |
| D-06 | Q-05 | GitHub + GitHub Actions | Utilisateur | 2026-10-05 | TRD §17, Plan T1.2 et §13 |
| D-07 | Q-08 | Endossement `AND(Org1MSP, Org2MSP)` | Utilisateur | 2026-10-05 | TRD §8.3 |
| D-08 | Q-06 | R3 : rapport PTB-XL d'origine ou texte FR saisi, lexique FR/DE/EN | Utilisateur | 2026-10-05 | PRD §13, TRD §21, Plan T3.11 |
| D-09 | Q-04 | Cible AUC macro ≥ 0,85 sur le fold 10 | Utilisateur | 2026-10-05 | PRD §5, Plan T3.8b |
| D-10 | — | Le projet comporte un volet **VHDL** : cœur **SHA-256** et filtre **FIR** de prétraitement ECG, en **P0** | Utilisateur | 2026-10-06 | Tous |
| D-11 | — | Intégration par **co-vérification** (simulation + carte), hors ligne : le pipeline n'appelle jamais la carte | Utilisateur | 2026-10-06 | PRD §7, TRD §5/§6.6, App Flow §1 |
| D-12 | — | Cible **Digilent Zybo Z7-10** (`xc7z010clg400-1`) ; Vivado ≥ 2023.x déjà installé ; travail porté par les membres **Ledger** (VHDL, Zynq, carte) et **IA** (coefficients, modèle de référence) ; mêmes 8 semaines / 4 personnes | Utilisateur | 2026-10-06 | PRD §12, TRD §3, Plan §3 |
| D-13 | — | La soutenance inclut une **étape matérielle en direct** (étape 9) | Utilisateur | 2026-10-06 | PRD §5/§8/§16, App Flow J-11, Plan T6.3/T6.5 |
| D-14 | Q-13 | La carte appartient à l'équipe et reste disponible tout le projet et le jour de la soutenance | Utilisateur | 2026-10-06 | PRD §13, TRD §19/§21, Plan §13 |
| D-15 | — | La présentation de vision (périmètre, choix techniques, prétraitement FIR, démo en 9 étapes, calendrier) est validée telle quelle par l'encadrant | Encadrant (rapporté par l'utilisateur) | 2026-10-23 (date de la validation `[TBD]`) | PRD (statut Approved), TRD, Plan |
| D-16 | Q-02 (date) | Soutenance le 2026-11-30 | Utilisateur | 2026-10-23 | PRD §12, Plan §7, §11 |
| D-17 | AAR-01 | Aucun développement depuis le 2026-10-06 : plan recalé sur 23/10 → 30/11 ; toutes les P0 conservées (dont VHDL) ; coupes : F-16/US-14 (saillance), écrans S-09/S-10 (remplacés par `scripts/registry.py`), tests d'utilisabilité à 2 testeurs ; jalons chevauchants | Utilisateur | 2026-10-23 | PRD, TRD, App Flow, Design Brief, Plan, traceability |
| D-18 | A-02.1, I-30 | Plan inchangé : périmètre P0 complet (VHDL, carte et étape 9 inclus), soutenance du 2026-11-30 maintenue, aucune coupe ni redistribution. L'équipe n'a rien commencé au 2026-11-09. Risque accepté : 64,5 j de tâches pour 64 j-personne au maximum (5 j/semaine), 51 j à 4 j/semaine, sans marge | Utilisateur (Nasr Siala) | 2026-11-09 | review.md, aar.md, Plan §12, PROGRESS.md |
| D-19 | — | Livraison par incrément : après chaque incrément, créer les tests (nouvelles fonctions, régression, anciens tests mis à jour), commit, push sur une branche portant le nom de l'incrément, merge request vers `main` ; plan d'implémentation dédié à L, itératif et incrémental | Utilisateur (Nasr Siala) | 2026-11-09 | AGENTS.md, Plan 08 (§1, §3, §4, §5), 08-implementation-plan-L.md |
