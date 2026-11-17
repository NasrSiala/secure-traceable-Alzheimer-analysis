# SAAMSTIAHF

Prototype pédagogique d'analyse d'ECG PTB-XL : pipeline LangGraph,
artefacts chiffrés hors chaîne, provenance sur Hyperledger Fabric et
co-vérification FPGA hors ligne. Ce prototype ne fournit pas un diagnostic médical.

Les [spécifications](docs/specs/08-implementation-plan.md), les
[règles de contribution](AGENTS.md) et le [suivi](PROGRESS.md) font référence.

## Démarrage du backend

Prérequis : Git et [uv](https://docs.astral.sh/uv/getting-started/installation/).
Python 3.11 est imposé par le projet ; uv peut l'installer automatiquement.

Depuis la racine du dépôt :

Sur le poste préparé le 17 novembre 2026, uv est installé localement dans
`.tools/`. Dans chaque nouvelle session PowerShell, ajouter son dossier au PATH :

```powershell
$env:PATH = (Join-Path (Get-Location).Path '.tools\Scripts') + ';' + $env:PATH
```

Avec une installation habituelle de uv, cette étape est inutile.

```powershell
uv sync --locked
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy saam
uv run --locked pre-commit install
```

Les versions exactes des outils sont conservées dans `uv.lock`.
Le fichier `.python-version` sélectionne Python 3.11 et `.venv/` contient
l'environnement propre au projet.

Pour préparer la configuration locale :

```powershell
Copy-Item .env.example .env
```

Renseigner les secrets localement avant de lancer les futurs services.
Le squelette ne charge pas encore ce fichier.

## Structure

- `saam/` : modules Python partagés par les processus API et worker.
  Chaque sous-module correspond à l'Architecture §5 ; `storage/` accueillera
  le stockage chiffré prévu par T3.2.
- `chaincode/provenance/`, `ledger-gateway/`, `fabric/` : contribution L.
- `frontend/` : contribution F.
- `ml/`, `saam/dsp/`, `saam/registry/` : contribution I.
- `hw/` : RTL, génération, simulation, build et outils de co-vérification.
- `scripts/` : outils d'administration et de démonstration.
- `tests/` : emplacements des suites prévues dans le plan.

T1.1 fournit les dossiers et les outils Backend. Les modules de `saam/`
contiennent uniquement leur description. Les dépendances applicatives du TRD §18
seront ajoutées à mesure que les tâches les utilisent.

La branche `backend` intègre désormais le travail de L présent dans `main` :
scripts Fabric, chaincode, passerelle et leurs tests. Le formatage Python commun
utilise 88 caractères. `pytest.ini` conserve les marqueurs et exclut par défaut
les tests qui nécessitent Fabric ou la carte.

Pour exécuter les tests locaux communs :

```powershell
uv run --locked pytest -q
```

La suite complète de L (Python et TypeScript) est `bash scripts/test-l.sh`,
avec Git Bash et Node disponibles. Les options `--fabric` et `--board` demandent
respectivement le réseau Docker et la carte ; les tests locaux n'en ont pas besoin.

La passerelle écoute par défaut sur le port 8080. Ses jetons sont lus dans
le fichier JSON `AGENT_TOKEN_FILE` ; la configuration et les identités sont
décrites dans `ledger-gateway/.env.example`.

La suite prévue est T1.2 (CI), puis T1.5 (pile Docker), selon les dépendances
du plan. Les contrôles d'architecture et la simulation relèvent de T1.11 et T1.10.

## Données

Utiliser uniquement les données publiques
[PTB-XL v1.0.3](https://physionet.org/content/ptb-xl/1.0.3/),
sous licence CC BY 4.0 : Wagner et al., *PTB-XL, a large publicly available
electrocardiography dataset*, Scientific Data 7, 154 (2020),
[doi:10.1038/s41597-020-0495-6](https://doi.org/10.1038/s41597-020-0495-6).

Les données téléchargées, les secrets, les volumes et les exports déchiffrés
de cas sont exclus de Git. Le pipeline reste indépendant du matériel (ADR-16).
