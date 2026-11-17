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

Pour préparer la configuration et le certificat TLS locaux :

```powershell
uv run --locked python scripts/prepare-stack.py
```

Le script crée `.env`, les jetons de service et le certificat dans `secrets/`,
sans afficher leurs valeurs. OpenSSL est nécessaire ; Git pour Windows le fournit.
Une seconde exécution conserve les fichiers existants. Si `.env` existe mais est
incomplet, le script indique les variables à renseigner sans le remplacer.
Les clés JWT et `ARTIFACT_KEY` seront utilisées par les tâches d'authentification
et de stockage ; elles ne sont pas nécessaires aux sondes de santé de T1.5.

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

T1.1 fournit les dossiers et les outils Backend. T1.5 ajoute l'API de santé,
le processus worker et le déploiement. Les dépendances applicatives du TRD §18
sont ajoutées à mesure que les tâches les utilisent.

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
respectivement le réseau Fabric et la carte. Docker est requis par les tests
PostgreSQL isolés de T1.11 et peut aussi fournir Node et GHDL sous Windows.

La passerelle écoute par défaut sur le port 8080. Ses jetons sont lus dans
le fichier JSON `AGENT_TOKEN_FILE` ; la configuration et les identités sont
décrites dans `ledger-gateway/.env.example`.

## Intégration continue (T1.2)

Le workflow [CI](.github/workflows/ci.yml) s'exécute sur les pushes vers `backend`
et `main`, ainsi que sur chaque pull request vers `main`. Le contrôle GitHub
`validation` vérifie Ruff, Mypy, ESLint et TypeScript, lance les tests locaux
Python et Jest, puis construit les images Docker sans les publier : base Python,
API, worker, passerelle, chaincode et nginx.
Il utilise Python 3.11, uv 0.13.8 et Node 20.20.2 avec les fichiers de verrouillage.

Pour préparer les paquets Node et reproduire leur lint depuis la racine :

```powershell
npm ci --ignore-scripts --prefix chaincode/provenance
npm ci --ignore-scripts --prefix ledger-gateway
npm run lint --prefix chaincode/provenance
npm run lint --prefix ledger-gateway
```

Avec Docker démarré, construire les cibles :

```powershell
docker build --target backend-base --tag saam-backend-base:local .
docker build --target api --tag saam-api:local .
docker build --target worker --tag saam-worker:local .
docker build --target ledger-gateway --tag saam-ledger-gateway:local .
docker build --target chaincode --tag saam-chaincode:local .
docker build --target frontend --tag saam-frontend:local .
```

`backend-base` fournit l'environnement Python des deux processus. La passerelle et
le chaincode compilent leur TypeScript dans une étape séparée, puis tournent
avec les seules dépendances de production et l'utilisateur `node`.
Leur démarrage nécessite les identités et la configuration Fabric décrites
dans `ledger-gateway/.env.example` et `chaincode/provenance/package.json`.
La pile complète est décrite ci-dessous.

Pour terminer T1.2, un administrateur doit ouvrir **Settings → Branches →
Add branch protection rule**, cibler `main`, puis activer :

- **Require a pull request before merging**, avec une approbation requise ;
- **Require status checks to pass before merging**, avec le contrôle `validation` ;
- **Require branches to be up to date before merging** ;
- **Do not allow bypassing the above settings**.

Conserver les pushes forcés et suppressions de branche désactivés. Une CI rouge
ne bloque effectivement la fusion que lorsque cette règle est active.
La [CI normale](https://github.com/NasrSiala/secure-traceable-Alzheimer-analysis/actions/runs/43998434040)
a passé tous les contrôles et les builds. Une
[sonde temporaire](https://github.com/NasrSiala/secure-traceable-Alzheimer-analysis/actions/runs/43999103520)
a confirmé qu'une assertion fausse rend `validation` rouge ; elle a ensuite été
retirée. Le blocage effectif d'une PR rouge reste à vérifier après activation de
la protection. La PR #10 reste en brouillon pour la revue de l'équipe ; le compte
Backend n'a pas les droits administrateur.

Les contrôles d'architecture T1.11 et la simulation T1.10 font aussi partie de
`validation`.

## Pile locale (T1.5)

Le [Compose](docker-compose.yml) démarre cinq services : PostgreSQL 16, API FastAPI,
worker, passerelle ledger et nginx. Seul nginx publie les ports 80/443 sur
`127.0.0.1`. Le worker n'expose aucun port et seul `ledger-gateway` monte le wallet
Fabric en lecture seule. API et worker utilisent les comptes `app_api` et
`app_worker`, sans droits administrateur.

Au démarrage de la passerelle, une courte initialisation privilégiée copie le
wallet dans un tmpfs privé, puis lance Node sous uid 1000 sans capacités Linux.
Les clés temporaires sont en mode 0600 ; les permissions du wallet hôte ne sont
pas modifiées. Le réseau d'entrée de nginx permet la publication HTTPS, séparément
du réseau interne des services Python et PostgreSQL.

Pour le premier démarrage, avec un réseau Fabric de test neuf et vide :

```powershell
uv run --locked python scripts/prepare-stack.py
bash fabric/network.sh start
bash fabric/enroll-identities.sh
docker compose up -d --build --wait --wait-timeout 180
curl.exe --insecure --fail https://localhost/api/v1/health
```

Sous Linux, remplacer `curl.exe` par `curl`. Git Bash et Docker sont nécessaires
aux commandes Fabric. `network.sh start` reconstruit un réseau qui n'est pas sain :
pour un réseau existant à conserver, vérifier d'abord son état avec
`bash fabric/network.sh status`, sans le réinitialiser. L'enrôlement doit fournir
les neuf identités et le chaincode `provenance` avant de lancer la passerelle.

Le certificat auto-signé couvre `localhost` et `127.0.0.1` pendant 30 jours.
Les ports peuvent être changés avec `HTTP_PORT` et `HTTPS_PORT` dans `.env`.

`GET /api/v1/health` est public. Il renvoie `200` avec `status: "ok"`, les cinq
services, `version` et `model` si tout est disponible. Une panne renvoie `503`,
`status: "degraded"` et le nom du service en erreur, sans détail de connexion.
La sonde ledger effectue une lecture Fabric sans écriture : un artefact absent
confirme que le chaincode répond ; un simple 404 de route ne suffit pas.
L'état du worker vient d'un fichier de statut récent partagé en lecture seule
avec l'API. OpenAPI est disponible sur `/api/v1/openapi.json`.

T1.5 crée seulement les comptes PostgreSQL ; les tables et leurs privilèges
applicatifs viendront avec la migration T2.1. `model` vaut donc `null` jusqu'à
l'enregistrement et l'activation d'un modèle. Le worker surveille sa connexion
à la base ; la prise de jobs et le graphe LangGraph sont T3.5. Le service
`frontend` fournit le proxy TLS, prêt à servir le bundle React de F ; les écrans
ne sont pas créés dans cette étape.

Pour vérifier les pannes et le retour au vert sur la pile déjà démarrée :

```powershell
$env:SAAM_TEST_STACK = '1'
uv run --locked pytest tests/integration/test_stack_health.py -q
Remove-Item Env:SAAM_TEST_STACK
uv run --locked python scripts/stack-status.py
```

Ces quatre tests arrêtent puis redémarrent uniquement `worker`, `ledger-gateway`
et `postgres` du projet `saam-stack`. Le rapport mémoire est conservé dans
`.tools/t15-stack-status.json`, ignoré par Git. Il mesure le socle et le réseau
Fabric ; il faudra refaire la mesure quand le modèle PyTorch sera chargé.

Pour arrêter les cinq services tout en conservant les volumes :

```powershell
docker compose stop
```

`docker compose start` les relance si le réseau Fabric est toujours disponible.
Les étapes Backend sont testées et poussées successivement sur `backend` ; la
fusion commune est prévue une fois les étapes terminées et relues par l'équipe.

## Simulation matérielle — T1.10

Le job GitHub Actions `hw-sim` exécute GHDL et cocotb à chaque push et PR.
La suite `validation` lance également la simulation : une assertion matérielle
en échec rend ce contrôle rouge, même si les tests Python et TypeScript passent.
La protection de `main` décrite plus haut reste à activer avant la fusion finale.

Sous Linux, installer Make et GHDL ≥ 3, puis utiliser l'environnement verrouillé :

```bash
uv sync --locked
make -C hw/sim
```

Sous Windows, le lanceur utilise Docker lorsque Make/GHDL sont absents :

```powershell
bash scripts/test-hw.sh
```

L'image de simulation contient uniquement les modules Python et le banc ; elle
ne monte aucun wallet ni carte et n'expose aucun port. Son exécution est sans
réseau. La construction initiale télécharge Ubuntu, GHDL et Python 3.11.
`scripts/test-l.sh` choisit automatiquement ce même lanceur pour sa simulation.

Le banc `smoke` teste un registre VHDL-2008 de huit bits : capture des 256 octets,
maintien de la sortie entre les fronts et remise à zéro asynchrone `aresetn`.
Il vérifie le fonctionnement des outils. Les cœurs SHA-256/FIR et leur comparaison
aux oracles Python restent T3.18/T3.19 ; les cibles `TEST=sha256`, `fir` et `axi`
seront ajoutées avec ces travaux. Une cible encore inconnue échoue explicitement.
Les sorties `sim_build/`, `results.xml` et les traces restent exclues de Git.

## Contrôles d'architecture — T1.11

```powershell
uv run --locked lint-imports --no-cache
uv run --locked pytest tests/arch tests/db/test_grants.py -q
```

Les contrats import-linter contrôlent les couches Python et interdisent les
imports de l'API vers le pipeline, ainsi que les imports du backend vers les
outils matériels et les SDK Fabric directs. Les tests AST précisent les
dépendances autorisées par l'Architecture §5–§8 et refusent les imports directs
des modèles d'un autre domaine. L'exception explicite de §8 autorise la future
interface `saam.pipeline.logs.list_for_case`, en lecture seule ; le module de
logs ne doit pas importer le pipeline d'exécution. La bibliothèque `storage`
reste privée à `traceability`, conformément à T3.2.

Les contrôles de propriété couvrent les 13 tables canoniques et les checkpoints
du schéma `langgraph`. Ils analysent les requêtes SQL littérales, les constantes
et concaténations résolubles exécutées par `execute`/`executemany`, ainsi que les
déclarations `__tablename__`. Les noms de tables dynamiques non résolubles sont
refusés. Les expressions ORM devront recevoir leur contrôle de liaison aux
modèles lors de leur introduction. Les futurs bancs SHA-256/FIR doivent importer
et appeler les oracles `saam.hashing` et `saam.dsp.fir_fixed`.

Le test des grants démarre un PostgreSQL 16.15 temporaire, applique
`docs/specs/schema.sql` sans le modifier, puis contrôle les droits des tables,
colonnes, séquences, schémas et rôles. Des commandes `SET LOCAL ROLE` vérifient
aussi les autorisations et refus réels, avec le code PostgreSQL `42501` attendu.
Les transactions sont annulées ; aucun cas n'est créé. Le conteneur n'expose
aucun port, utilise `--network=none` et stocke ses données en tmpfs. Seul ce
conteneur est retiré après le test. Docker doit fonctionner ; la première
exécution télécharge l'image épinglée par digest.

Ces tests vérifient le schéma de référence. La conformité des migrations et de
la base applicative sera vérifiée en T2.1. Une copie temporaire du paquet permet
de tester qu'import-linter refuse les imports interdits et accepte l'interface
de lecture des logs, sans modifier le code applicatif.

## Données

Utiliser uniquement les données publiques
[PTB-XL v1.0.3](https://physionet.org/content/ptb-xl/1.0.3/),
sous licence CC BY 4.0 : Wagner et al., *PTB-XL, a large publicly available
electrocardiography dataset*, Scientific Data 7, 154 (2020),
[doi:10.1038/s41597-020-0495-6](https://doi.org/10.1038/s41597-020-0495-6).

Les données téléchargées, les secrets, les volumes et les exports déchiffrés
de cas sont exclus de Git. Le pipeline reste indépendant du matériel (ADR-16).
