# SAAMSTIAHF — After Action Reviews

Suite version : 2.0.1 — 2026-10-23. Un AAR à chaque checkpoint de jalon (M1–M6), après une release, un incident, un retour arrière, ou un changement de suite touchant 3 documents ou plus. Format : prévu, réel, pourquoi l'écart, à garder, à changer, actions (responsable + échéance). Sans reproche : on décrit des décisions et des conditions, jamais des fautes individuelles.

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
| A-01.1 | Nommer les 4 membres et leur rôle L/I/B/F (ferme Q-11) | Équipe | 2026-10-24 | Plan §3 ; review.md Q-11 | open |
| A-01.2 | Créer le dépôt GitHub, protéger `main`, y pousser `docs/`, `AGENTS.md`, `PROGRESS.md` (début de T1.1, T1.2) | B | 2026-10-26 | T1.1, T1.2 | open |
| A-01.3 | Recaler le plan sur 23/10 → 30/11 avec coupes et rééquilibrage | Claude, validé par l'équipe | 2026-10-23 | Plan v2.0.0 ; D-17 ; CHANGELOG v2.0.0 | done |
| A-01.4 | Confirmer avec l'encadrant son nom et les dates des portes M2 (2026-11-03) et M6 (2026-11-27) | Équipe | 2026-10-27 | review.md Q-12 ; Plan §7 | open |
| A-01.5 | Tenir un point hebdomadaire le vendredi (premier le 2026-10-30) : `PROGRESS.md` à jour + actions AAR revues | Équipe | 2026-10-30 | AGENTS.md (checkpoint) ; Plan §4 | open |
| A-01.6 | Identifier les autres causes du démarrage tardif et les ajouter à cet AAR | Équipe | 2026-10-27 | aar.md AAR-01 | open |

Prochain AAR : AAR-02, checkpoint M1 (≤ 2026-10-28). Il commence par l'état des actions A-01.1 à A-01.6 ; une action encore ouverte à AAR-03 est escaladée.
