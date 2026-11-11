# SAAMSTIAHF — After Action Reviews

Suite version : 2.1.3 — 2026-11-09. Un AAR à chaque checkpoint de jalon (M1–M6), après une release, un incident, un retour arrière, ou un changement de suite touchant 3 documents ou plus. Format : prévu, réel, pourquoi l'écart, à garder, à changer, actions (responsable + échéance). Sans reproche : on décrit des décisions et des conditions, jamais des fautes individuelles.

Gabarit :

```markdown
## AAR-NN — [périmètre] — [date]
**Scope:** [jalon, tâches]  **Participants:** [noms/agents]
**Previous actions:** [A-xx.y done / open (escalated)]

| | Planned | Actual | Evidence |
|---|---|---|---|

**Why the gap**
**Keep**
**Change**
**Actions**
| ID | Action | Owner | Due | Lands in | Status |
|---|---|---|---|---|---|
```

## AAR-01 — Démarrage : M1 et M2 non commencés — 2026-10-23

**Scope :** plan v1.1.0, M1 (T1.1–T1.10) et M2 (T2.1–T2.12).  **Participants :** équipe projet (4 membres), Claude (rédaction de la suite).
**Previous actions :** aucune (premier AAR).

| | Planned | Actual | Evidence |
|---|---|---|---|
| Périmètre | M1 et M2 terminés : 22 tâches | 0 tâche commencée ; aucun dépôt git | `PROGRESS.md` inchangé depuis le 2026-10-06 ; dossier projet sans `.git` |
| Date M1 | 2026-10-11 | Non atteinte | — |
| Date M2 + porte encadrant | 2026-10-18 | Non atteinte ; vision validée par l'encadrant hors plan, telle quelle (date `[TBD: à noter par l'équipe]`) | D-15 |
| Specs | v1.1.0 au 2026-10-06 | v1.1.0 livrée le 2026-10-06 ; présentation de vision le 2026-10-07 | CHANGELOG v1.1.0 ; `docs/presentation/` |
| Question bloquante de M1 | Q-11 (noms et rôles) due le 2026-10-06 | Toujours ouverte au 2026-10-23 | review.md |

**Why the gap**
- Le plan v1.0.0/v1.1.0 faisait démarrer M1 le 2026-10-05, alors que les specs étaient encore en rédaction et que la vision n'était pas validée ; il n'avait aucune porte d'entrée « vision validée, équipe nommée ». (Le plan était faux : date de début irréaliste, pas de kickoff.)
- Aucune tâche n'avait de personne nommée (Q-11 ouverte), donc personne n'était responsable de lancer T1.1. (Plan §3 et review.md : rôles sans noms.)
- `PROGRESS.md` n'était pas tenu et aucun point d'avancement n'était prévu, donc le retard est resté invisible jusqu'au 2026-10-23. (Processus manquant.)
- Autres causes possibles (disponibilité, examens, accès au matériel) : `[TBD: à confirmer par l'équipe, A-01.6]`.

**Keep**
- Specs complètes et cohérentes avant de coder.
- Présentation de vision courte : elle a obtenu la validation de l'encadrant sans modification.

**Change**
- Nommer les responsables avant la première tâche ; une tâche sans personne nommée ne compte pas comme planifiée.
- Point d'avancement hebdomadaire court : `PROGRESS.md` à jour et revue des actions AAR.
- Plan recalé du 2026-10-23 au 2026-11-30, jalons chevauchants et coupes (D-17).

**Actions**

| ID | Action | Owner | Due | Lands in | Status |
|---|---|---|---|---|---|
| A-01.1 | Nommer les 4 membres et leur rôle L/I/B/F (ferme Q-11) | Équipe | 2026-10-24 | Plan §3 ; review.md Q-11 | partial — L nommé (2026-11-09) ; I, B, F repris par A-02.3 (escaladée) |
| A-01.2 | Créer le dépôt GitHub, protéger `main`, y pousser `docs/`, `AGENTS.md`, `PROGRESS.md` (début de T1.1, T1.2) | B | 2026-10-26 | T1.1, T1.2 | done — dépôt GitHub créé et docs poussées le 2026-10-23 (db882b2) ; protection de `main` non vérifiée |
| A-01.3 | Recaler le plan sur 23/10 → 30/11 avec coupes et rééquilibrage | Claude, validé par l'équipe | 2026-10-23 | Plan v2.0.0 ; D-17 ; CHANGELOG v2.0.0 | done |
| A-01.4 | Confirmer avec l'encadrant son nom et les dates des portes M2 (2026-11-03) et M6 (2026-11-27) | Équipe | 2026-10-27 | review.md Q-12 ; Plan §7 | open — escaladée, reprise par A-02.4 |
| A-01.5 | Tenir un point hebdomadaire le vendredi (premier le 2026-10-30) : `PROGRESS.md` à jour + actions AAR revues | Équipe | 2026-10-30 | AGENTS.md (checkpoint) ; Plan §4 | open — escaladée, reprise par A-02.5 |
| A-01.6 | Identifier les autres causes du démarrage tardif et les ajouter à cet AAR | Équipe | 2026-10-27 | aar.md AAR-01 | open — escaladée, reprise par A-02.6 |

Prochain AAR : AAR-02, checkpoint M1 (≤ 2026-10-28). Il commence par l'état des actions A-01.1 à A-01.6 ; une action encore ouverte à AAR-03 est escaladée.

## AAR-02 — Checkpoint M1 manqué ; M2 non approuvée — 2026-11-09

**Scope :** M1 (T1.1–T1.11, échéance 2026-10-28) ; état de M2 (T2.1–T2.12, porte encadrant 2026-11-03, son AAR sera AAR-03).  **Participants :** Nasr Siala (L), Claude. Rôles I, B, F : 0 tâche commencée (déclaré le 2026-11-09).
**Previous actions :** A-01.1 partial (L nommé, I/B/F non) ; A-01.2 done ; A-01.3 done ; A-01.4, A-01.5, A-01.6 open depuis AAR-01 → escaladées à l'utilisateur.

| | Planned | Actual | Evidence |
|---|---|---|---|
| Rôle L, M1–M2 | 8 tâches faites : T1.3, T1.4, T1.8, T1.9, T2.5a, T2.5b, T2.6, T2.9 | 0 commencée ; 0 sur les 18 tâches de L | Déclaration de Nasr Siala, 2026-11-09 |
| Rôles I, B, F, M1–M2 | 16 tâches faites : T1.1, T1.2, T1.5–T1.7, T1.10, T1.11, T2.1–T2.4, T2.7, T2.8, T2.10–T2.12 | 0 commencée | Déclaration de Nasr Siala pour l'équipe, 2026-11-09 |
| Dépôt | M1 fait : T1.1, T1.2, T1.10, T1.11 (B) | Un seul commit (db882b2, 2026-10-23, docs seulement) ; `origin/main` identique ; arbre propre | `git log`, `git status` au 2026-11-09 |
| Suivi | `PROGRESS.md` à jour à chaque tâche et chaque point hebdo | Aucune ligne « Fait » ; fichier inchangé depuis 2026-10-23 | `PROGRESS.md` |
| Date M1 | 2026-10-28 | Non atteinte, 12 jours de retard | — |
| Porte M2 | 2026-11-03 | `[TBD: a-t-elle eu lieu ? réponse de l'encadrant, Q-15]` | — |
| Capacité | L : 17,6 j de tâches ; équipe : 64,5 j (Plan §3) | 16 jours ouvrés du 2026-11-09 au 2026-11-30 : L ≈ 13 j ; équipe ≈ 51 j à 4 j/semaine ou 64 j à 5 j/semaine. Déficit : L ≈ 4,6 j, équipe ≈ 13 j à 4 j/semaine, avant toute attente de dépendance | Plan §3, §11 ; calcul |

**Why the gap**
- Les changements décidés à l'AAR-01 n'ont pas pris effet : le point hebdomadaire (A-01.5, premier le 2026-10-30) n'a laissé aucune trace et `PROGRESS.md` n'a pas bougé, donc le retard est resté invisible deux semaines de plus. (Processus : aucune action n'avait de rappel ni de preuve attendue.)
- Le plan recalé v2.0.0 n'avait aucune marge de calendrier (Plan §12) et le chemin critique T1.3 → T1.4 → T2.5a → T2.6 → T2.7 → T3.3 reposait sur le seul rôle L ; ce retard se propage donc directement à B et à la porte M2. (Plan fragile : chemin critique sans marge ni doublure.)
- Cause du non-démarrage (L, I, B, F) : `[TBD: à confirmer par l'équipe, A-02.6]`. Cet AAR n'en suppose aucune.

**Keep**
- Spécifications complètes et cohérentes ; dépôt GitHub créé et poussé.
- État rapporté sans détour le 2026-11-09 : il permet de recaler tout de suite.

**Change**
- Écrire l'état dans `PROGRESS.md` à chaque point hebdomadaire, même quand rien n'a été fait.
- Décider explicitement du plan après un retard : D-18 a conservé le plan tel quel, avec un risque de calendrier accepté ; le revoir à chaque point hebdomadaire.
- Faire démarrer d'abord le chemin critique (chaîne Fabric) et le vérifier en deux jours, pas en fin de jalon.

**Actions**

| ID | Action | Owner | Due | Lands in | Status |
|---|---|---|---|---|---|
| A-02.1 | Décider du recalage 2026-11-09 → 2026-11-30 : coupes ou redistribution (L ≈ 13 j pour 17,6 j) ; enregistrer D-18 ; mettre le plan à jour | Nasr Siala (L) + équipe ; décision de l'utilisateur | 2026-11-10 | Plan (version mineure ou majeure selon les coupes) ; review.md D-18, I-30 ; CHANGELOG | done — D-18 (2026-11-09) : plan inchangé, risque de calendrier accepté |
| A-02.2 | Démarrer T1.3 puis T1.4 (chaîne Fabric, chemin critique de B) | Nasr Siala (L) | T1.3 : 2026-11-10 ; T1.4 : 2026-11-12 | `PROGRESS.md` (Fait) | open |
| A-02.3 | Nommer I, B et F (ferme Q-11, reprend A-01.1) | Équipe | 2026-11-10 | Plan §3 ; review.md Q-11 | open (escaladée) |
| A-02.4 | Savoir ce qui s'est passé à la porte M2 du 2026-11-03 ; obtenir nom et dates de l'encadrant (reprend A-01.4) | Nasr Siala (L) | 2026-11-11 | review.md Q-12, Q-15 ; Plan §7 | open (escaladée) |
| A-02.5 | Point hebdomadaire le vendredi (13/11, 20/11, 27/11) avec `PROGRESS.md` à jour, y compris « rien fait » (reprend A-01.5) | Équipe | 2026-11-13 | AGENTS.md ; `PROGRESS.md` | open (escaladée) |
| A-02.6 | Compléter cet AAR : cause du non-démarrage de l'équipe (reprend A-01.6) ; l'état de I, B, F est connu : 0 tâche | Nasr Siala (L) | 2026-11-11 | aar.md AAR-02 | open (escaladée) |

Prochain AAR : AAR-03, checkpoint M2 (porte à replanifier par A-02.1). Il commence par l'état des actions A-02.1 à A-02.6.
