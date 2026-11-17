# PROGRESS — SAAMSTIAHF

Suite de specs : v2.0.1 (2026-10-23). Mettre à jour à la fin de chaque tâche.

## Courant

- **Jalon :** M1 — Mise en place (23/10 → 28/10 ; plan recalé, D-17)
- **Avant toute tâche :** actions A-01.1 (noms et rôles) et A-01.2 (dépôt GitHub) de [docs/specs/aar.md](docs/specs/aar.md)
- **État au 2026-11-17 :** T1.1 terminée sur la branche `backend`. Les dates ci-dessus restent celles du plan publié ; le jalon M1 complet n'est pas validé.
- **Tâche suivante B :** T1.2 CI ; puis T1.5 Docker, T1.10 simulation et T1.11 contrôles d'architecture selon leurs dépendances.
- **Débloqué par T1.1 pour l'équipe :** T1.3 Spike Fabric (L), T1.6 PTB-XL (I), T1.7 Frontend (F), T1.9 Spike Zybo (L). Leur réalisation hors de cette branche n'est pas vérifiée.
- **Bloquants :** voir questions ouvertes dans `docs/specs/review.md`

## Fait

| Tâche | Date | Preuve (commande / lien) |
|---|---|---|
| T1.1 — squelette du monorepo, environnement uv, configuration et hooks pre-commit | 2026-11-17 | Python 3.11.18 ; `uv sync` ; `uv run --locked ruff check .` ; `uv run --locked ruff format --check .` ; `uv run --locked mypy saam` (13 fichiers) ; `uv run --locked pre-commit validate-config` ; `uv run --locked pre-commit install` ; les 3 hooks exécutés sur les fichiers de `saam/` passent ; `git diff --check` |

Vérification effectuée sur Windows avec uv 0.13.8 installé dans `.tools/`,
environnement `.venv/` et versions figées dans `uv.lock`. Les commandes de
contrôle ont été exécutées hors ligne après synchronisation. Le cache uv,
le Python géré et le cache pre-commit sont placés dans `.tools/` (ignoré par Git).
Les modules sont des squelettes : aucun test métier n'est encore présent et
aucune réussite de tests applicatifs n'est annoncée. Les contrôles T1.10/T1.11
et les vérifications TypeScript attendent leurs tâches.

## Décisions (prises pendant le build)

| Date | Décision | Contexte | Reportée dans les specs ? |
|---|---|---|---|
| 2026-11-17 | Continuer sur la branche exacte `backend`, demandée par l'utilisateur dans la prise en main | T1.1 ; branche déjà existante, aucun changement de branche | Non, préférence de travail |
| 2026-11-17 | Déclarer les outils de développement maintenant et les dépendances applicatives du TRD §18 dans les tâches qui les utilisent | T1.1 crée la structure sans implémenter les services ; aucune nouvelle dépendance métier | Non, mise en place |

## Problèmes

| Date | Problème | Tâche | Statut |
|---|---|---|---|
| 2026-11-17 | A-01.1 / Q-11 : rôle B de l'utilisateur confirmé dans le chat précédent ; noms des quatre membres encore absents des sources | Coordination équipe | Ouvert ; non bloquant pour T1.1 selon review.md |
| 2026-11-17 | A-01.2 : dépôt GitHub et branche backend existent ; protection de main à vérifier | T1.2 | Partiellement réalisé, pas clôturé |

## Trouvé, non construit

| Date | Idée / besoin | Où | Proposé pour |
|---|---|---|---|
| | | | |
