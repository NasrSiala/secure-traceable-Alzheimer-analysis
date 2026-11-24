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
Les clés JWT et AES sont requises pour l'authentification et les traitements.
La clé AES (32 octets, 64 caractères hexadécimaux) est créée uniquement pour
un nouvel environnement. Pour un `.env` existant, renseigner `ARTIFACT_KEY`
ou `ARTIFACT_KEY_FILE` avec la clé déjà utilisée, puis relancer le script.
Celui-ci prépare `secrets/artifact-key.hex`, monté en lecture seule dans l'API
et le worker ; il refuse une différence avec un secret existant. Conserver
cette clé avec les sauvegardes : sa perte empêche de déchiffrer les artefacts.

## Structure

- `saam/` : modules Python partagés par les processus API et worker.
  Chaque sous-module correspond à l'Architecture §5 ; `storage/` fournit
  le stockage AES-256-GCM de T3.2.
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

## Hachage des artefacts

Le stockage `saam.storage.ArtifactStore` (T3.2) chiffre chaque fichier avec
AES-256-GCM. Le format sur disque est nonce de 12 octets, contenu chiffré et
tag de 16 octets ; l'AAD est `artifact_id|name`. La clé de 32 octets est injectée
ou chargée depuis `ARTIFACT_KEY` (64 caractères hexadécimaux) ou le fichier
secret `ARTIFACT_KEY_FILE`. `ARTIFACT_ROOT` désigne la racine du stockage.
Les fichiers sont écrits atomiquement ; un nonce, contenu ou tag altéré, une
mauvaise clé ou une substitution de fichier provoquent `DecryptionError`.
Les chemins traversants et liens symboliques sont refusés.

Vérification : `uv run --locked pytest tests/storage -q`.

`TraceabilityTool.record` (T3.3) écrit les fichiers chiffrés et le manifeste,
commite les lignes PostgreSQL en `en_attente`, puis ancre avec une tentative
et trois réessais (attentes 1/2/4 s). Un doublon n'est accepté que si la preuve
Fabric correspond au même artefact. Une erreur définitive appelle le service
des cas injecté par `on_failure` ; la traçabilité ne modifie pas ses tables.
Les lectures comparent le manifeste et ses fichiers à l'empreinte Fabric,
indépendamment de la copie d'affichage PostgreSQL.

La passerelle expose l'identifiant de transaction dans le header
`X-Fabric-Transaction-Id` des écritures/lectures d'artefacts ; le client Python
le rend dans `txId`. La requête Fabric en lecture seule `GetArtifactReceipt`
le retrouve dans l'historique de la clé, y compris après une réponse perdue.
Le schéma des enregistrements et historiques on-chain reste inchangé.
Le réseau doit déployer le chaincode de ce commit et garder l'historique
Fabric activé (configuré explicitement sur les deux pairs).

`POST /api/v1/cases` (T3.4) accepte un multipart `ecg_files[]`,
`csv_sampling_rate` pour un CSV, et `report_file` ou `report_text` facultatif.
Il valide les 12 dérivations, la durée minimale de 10 secondes, la fréquence
50–10 000 Hz et les 20 Mo d'ECG ; le rapport UTF-8 est limité à 10 000 caractères.
Les messages reprennent S-03. Operator/admin peuvent créer ; auditor est refusé.
La réponse 202 contient id, case_ref et status=en_attente, avec un header Location.

Le transit API/worker reste chiffré dans le volume `/data/uploads` : l'API écrit
et le worker lit. Le volume d'artefacts reste en lecture seule pour l'API.
Les noms sont régénérés ; les références internes WFDB sont ajustées.
Cas, job et événement d'audit sont insérés dans la même transaction, avec
rollback du nouveau transit en cas d'échec. Une limite de dix créations par
minute/utilisateur est partagée entre instances via PostgreSQL.
Nginx laisse une marge pour le multipart et transmet sans mise en tampon sur disque.

Vérification : `uv run --locked pytest tests/api/test_cases_create.py -q`.

`saam.hashing` fournit `canonical_manifest`, `artifact_hash` et `file_hash`
(IF-05, T3.1). L'empreinte de l'artefact est le SHA-256 du manifeste JCS
RFC 8785 : fichiers triés par nom, flottants arrondis à six décimales.
La canonisation conserve les identifiants et horodatages fournis et ne modifie
pas le manifeste en mémoire.

Le producteur prépare les fichiers JSON avec `canonical_json` et les textes
avec `canonical_text` (UTF-8 NFC). `file_hash` hache les octets exacts ; les
fichiers binaires CSV/WFDB/NPY doivent déjà respecter leur format canonique.
Le manifeste consigne la taille et l'empreinte des octets clairs ainsi préparés.
Le stockage chiffré et l'ancrage sont les étapes T3.2 et T3.3.

`uv run --locked pytest tests/hashing -q` vérifie notamment un manifeste
de référence et son empreinte 100 fois. La CI exécute cette même suite sur
Ubuntu et Windows pour vérifier NFR-12.

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

La preuve GitHub sur la PR #10 comprend un
[vert initial](https://github.com/NasrSiala/secure-traceable-Alzheimer-analysis/actions/runs/44158596871)
(`1615333`), puis une
[sonde rouge](https://github.com/NasrSiala/secure-traceable-Alzheimer-analysis/actions/runs/44159412733)
(`61ec051`) : l'import `saam.api.architecture_probe` → `saam.pipeline` rend le
contrat BROKEN et `validation` échoue avec exit 1, après les lints verts.
La sonde est retirée ; le code applicatif retrouve exactement celui du vert
initial. Le
[retour au vert sur la PR](https://github.com/NasrSiala/secure-traceable-Alzheimer-analysis/actions/runs/44160056234)
et le
[push restauré vert](https://github.com/NasrSiala/secure-traceable-Alzheimer-analysis/actions/runs/44160043940)
(`700aeb9`) confirment les trois contrats, les 62 tests ciblés, la régression
complète et les six builds Docker. Aucun test n'est affaibli.

## Migration initiale — T2.1

La migration Alembic `0001_initial` contient un snapshot figé de `schema.sql`
(13 tables, contraintes, index, enums, triggers et permissions). Le document
canonique reste la référence indépendante des tests. Alembic gère une seule
transaction, incluant sa table de version ; un échec annule toutes les créations.

Configurer localement `DATABASE_URL_MIGRATIONS` avec un compte administrateur
PostgreSQL, puis exécuter depuis la racine :

```powershell
uv run --locked alembic upgrade head
uv run --locked pytest tests/db/test_migration.py -q
```

Cette connexion administrative n'est pas fournie aux processus API/worker.
Le rollback `alembic downgrade -1` conserve les rôles et leurs secrets ; il
refuse de supprimer par cascade des dépendances ajoutées hors migration.
En démo, utiliser la restauration de sauvegarde. Les tests utilisent un
PostgreSQL jetable publié uniquement sur un port localhost aléatoire, avec
données en tmpfs ; aucun volume de la pile applicative n'est modifié.

## Initialisation — T2.2

Après la migration, renseigner localement les six variables `SEED_*_EMAIL` et
`SEED_*_PASSWORD` de `.env`, puis exécuter :

```powershell
uv run --locked python scripts/seed.py
uv run --locked python scripts/seed.py
```

Le script utilise `DATABASE_URL_API` et le rôle `app_api`, sans privilège
administrateur. Il crée un admin, un operator et un auditor avec mots de passe
Argon2id (12 caractères minimum), puis la configuration v1 : seuil 0,700,
qualité 0,900 et lexique `v1`. Les variables d'environnement priment sur le
fichier `.env` ; `--env-file` permet d'utiliser un autre fichier privé.

Les deux exécutions conservent les mêmes identifiants et hashes. Les comptes
existants ne sont ni réactivés ni réinitialisés ; une configuration ultérieure
active reste active. Un rôle incompatible ou une configuration v1 différente
annule la transaction entière. Les mots de passe ne sont jamais affichés.
Le modèle sera enregistré par T3.9, après son entraînement, sans modèle factice.

## Attribution des données

## Authentification — T2.3

Configurer `JWT_SECRET` (au moins 32 octets de secret aléatoire) dans `.env`.
`prepare-stack.py` le génère pour les nouvelles configurations ; les fichiers
existants sont conservés. Après migration et seed, les routes sont :

- `POST /api/v1/auth/login` : JSON `email`, `password` ; réponse avec
  `access_token`, `token_type`, `expires_in=1800` et profil `user`.
- `POST /api/v1/auth/refresh` : authentification par le cookie de session,
  même après expiration du JWT ; émet un nouveau JWT et remplace le refresh.
- `POST /api/v1/auth/logout` : révoque le refresh courant, efface le cookie, 204.
- `GET /api/v1/me` : `Authorization: Bearer <access_token>` ; rôle et activation
  relus en base à chaque demande.

Le JWT utilise HS256, un issuer/audience fixes et une expiration de 30 minutes.
Le refresh opaque expire huit heures après la connexion initiale et reste en
cookie `saam_refresh`, `HttpOnly; Secure; SameSite=Strict`, limité à
`/api/v1/auth`. Seul son SHA-256 est stocké ; cette empreinte de secret opaque
est distincte du contrat de hachage des artefacts. La rotation est atomique,
à usage unique, sans prolongation des huit heures. La déconnexion révoque le
refresh ; un JWT déjà émis reste limité par son expiration de 30 minutes.

Cinq échecs en quinze minutes verrouillent le compte pour quinze minutes :
la cinquième tentative renvoie 401, la sixième 423. Les tentatives restent
enregistrées malgré le refus HTTP. La limite de dix connexions/minute/IP est
renforcée en PostgreSQL et partagée par les workers. nginx remplace le header
transmis `X-Forwarded-For` par l'adresse observée ; l'API reste sur le réseau
Docker privé et accepte ces informations du proxy.

Les requêtes de navigateur doivent provenir de `AUTH_ORIGIN` (défaut
`https://localhost`) ; les origines étrangères sont refusées. Les erreurs
suivent le format TRD et les messages français de l'App Flow. Ni les passwords
ni les tokens soumis ne sont renvoyés dans les erreurs de validation.

## Autorisation des routes — T2.4

`saam/api/authz.py` applique la matrice TRD §8–9 par dépendance FastAPI.
Une route applicative doit utiliser `AuthorizedRoute` et figurer dans
`ROUTE_POLICIES`. Les routeurs ajoutés utilisent
`APIRouter(prefix="/api/v1", route_class=AuthorizedRoute)` ; la création de
l'application et les tests refusent une route sans contrôle. Le rôle et
l'activation du compte sont relus en base à chaque requête protégée.

Les trois rôles consultent et vérifient les cas ; seuls operator/admin
créent un cas et seul admin gère les utilisateurs. Login et health sont
publics ; refresh/logout authentifient leur cookie de session. OpenAPI reste
accessible pour le contrat. Les droits des futures routes T3/T4 sont déclarés,
mais leurs fonctions métier ne sont pas créées par T2.4. Les seuils et modèles
restent administrés par les scripts prévus (D-17).

```powershell
uv run --locked pytest tests/api/test_authz.py -q
```

Les 44 tests couvrent les 36 cases de la matrice, les JWT réels pour les trois
rôles, les requêtes anonymes, les faux headers de rôle, la rétrogradation et
la désactivation après émission du JWT, OpenAPI et les routes sans règle.

## Client Python de la passerelle — T2.7

`saam.ledger.LedgerClient` expose l'interface synchrone IF-07 :
`create_record`, `get_record`, `get_case_history`, `register_model`, `get_model`.
Les domaines peuvent dépendre du protocole `Ledger` pour remplacer le transport.
La gateway reste seule à détenir les clés Fabric.

```python
from saam.ledger import LedgerClient, RecordNotFound

# Charger LEDGER_GATEWAY_URL et le jeton de cette identité dans l'environnement.
with LedgerClient.from_environment("verifier") as ledger:
    try:
        record = ledger.get_record("11111111-1111-4111-8111-111111111111")
    except RecordNotFound:
        record = None
```

Une instance porte un seul jeton `X-Agent-Token`. `from_environment` accepte
les sept noms d'agents courts, `verifier` et `model-admin`. Il lit le jeton
`AGENT_TOKEN_*` correspondant, ou cette seule identité dans `AGENT_TOKEN_FILE`.
Pour un appel depuis l'hôte, renseigner une URL de gateway accessible depuis
l'hôte ; `http://ledger-gateway:8080` est le défaut du réseau Docker interne.

Le délai HTTPX est de 10 s par opération réseau. Chaque méthode fait une seule
tentative : les reprises 1/2/4 s appartiennent à T3.3. Les redirections et les
proxies d'environnement sont désactivés. Les refus deviennent `LedgerForbidden`
(401/403), `RecordNotFound` (404), `DuplicateRecord` (409), `InvalidRecord`
(400/422) ou `LedgerUnavailable` (502, transport ou réponse invalide). Les
exceptions conservent `status`/`code` et un message français sans corps brut.

```powershell
uv run --locked pytest tests/ledger -q
```

Les tests démarrent l'application Fastify réelle sur loopback, avec un
adaptateur Fabric en mémoire, et vérifient création/lecture, les identités,
le schéma fermé et les refus. Ils requièrent Node et les dépendances Node
verrouillées. Les cinq contrats Python sont aussi vérifiés par transport HTTP
contrôlé, dont les réponses invalides, délais, redirections et chemins injectés.

Les routes d'historique et de modèles de T2.6 sont intégrées depuis `main`.
Les cinq méthodes du client sont testées contre Fastify réel avec un adaptateur
Fabric en mémoire : historique vide ou présent, modèles, identité model-admin,
doublons, absences et schéma fermé. Ces tests sont distincts des transactions
sur le réseau Fabric réel. Le garde NFR-03 utilise aussi ce client partagé.

## Cas, artefacts et orchestration — T3.2 à T3.5

Après migration et seed, `POST /api/v1/cases` accepte un JWT operator/admin
et un corps multipart : `ecg_files[]` (CSV ou paire WFDB),
`csv_sampling_rate` pour le CSV, et éventuellement `report_text` ou
`report_file`. La réponse 202 contient `id`, `case_ref`, `status=en_attente`
et un en-tête `Location`. L'ECG est limité à 20 Mo et le rapport UTF-8 à
10 000 caractères. Le CSV exige les douze dérivations, une fréquence entre
50 et 10 000 Hz et au moins dix secondes. Les erreurs utilisent les messages
de S-03 ; la limite est de dix créations/minute/utilisateur.

Les noms sont régénérés et le transit est chiffré dans `/data/uploads`
(API en écriture, worker en lecture seule). Cas, job et audit sont créés
dans une seule transaction. Le worker consomme la file FIFO avec
`FOR UPDATE SKIP LOCKED`, un seul job à la fois. Il exécute ingestion →
préparation → caractéristiques → prédiction → validation → explication →
finalisation. Chaque étape lit et vérifie son parent via la traçabilité,
stocke les fichiers chiffrés et ancre le manifeste sous son identité Fabric.

**T3.5 utilise sept agents factices : les sorties intermédiaires sont des
placeholders, sans modèle clinique ni LLM.** Le parcours normal produit sept
artefacts et la décision `revision_requise`. Une exception ou un rejet arrête
les étapes dépendantes et produit un résultat final `rejete` motivé et ancré.
Si l'ancrage échoue après une tentative et trois réessais (1/2/4 s), le cas
passe en `erreur_ancrage` et aucune décision finale n'est émise. Le traitement
réel, la pseudonymisation et l'entraînement relèvent des tâches T3.6–T3.12.
Utiliser uniquement des entrées publiques ou synthétiques pour cette tranche.

`ArtifactStore` chiffre en AES-256-GCM avec un nonce aléatoire de 12 octets
et l'AAD `artifact_id|name`. `TraceabilityTool.record` écrit les fichiers,
commite la ligne SQL `en_attente`, appelle Fabric, puis enregistre `ancre`
avec le reçu de transaction. Le rejeu conserve les identifiants et refuse un
contenu différent. Les lectures vérifient le manifeste contre Fabric et les
fichiers contre leurs empreintes. Le reçu `GetArtifactReceipt` est une requête
en lecture seule ; aucun contenu ECG/rapport ni clé AES n'est écrit sur la chaîne.

Les checkpoints LangGraph sont synchrones dans le schéma PostgreSQL
`langgraph` et contiennent seulement identifiants, états et codes de motif.
Le heartbeat reste actif pendant une étape longue. Après cinq minutes sans
heartbeat, un job est remis en file pour reprise ; trois tentatives épuisées
le font échouer. Une interruption entre ancrage et checkpoint peut rejouer
l'étape : l'artefact et son entrée de journal restent idempotents. Un ancien
worker perd le droit de terminer ou de faire échouer le cas.

`GET /api/v1/cases/{id}/agent-logs` permet aux trois rôles authentifiés de
consulter les agents, entrées/sorties, statuts et durées ; un cas absent
renvoie 404. L'API ne lance jamais le graphe et le pipeline n'appelle pas la carte.

```powershell
uv run --locked pytest tests/storage tests/pipeline tests/api/test_cases_create.py tests/api/test_pipeline_flow.py -q
```

Les tests utilisent PostgreSQL, AES-GCM et LangGraph réels. Le parcours HTTP
traverse FastAPI/JWT, le client Python, Fastify et le contrat TypeScript
Provenance, avec l'état et les certificats Fabric simulés en mémoire. Il
vérifie sept ancrages, parents, identités, reçus distincts et accès au journal.
Il ne constitue pas une validation sur un réseau Fabric déployé ; celle-ci
reste distincte de la suite locale, comme les tests sur la carte.

## Source des données

Utiliser uniquement les données publiques
[PTB-XL v1.0.3](https://physionet.org/content/ptb-xl/1.0.3/),
sous licence CC BY 4.0 : Wagner et al., *PTB-XL, a large publicly available
electrocardiography dataset*, Scientific Data 7, 154 (2020),
[doi:10.1038/s41597-020-0495-6](https://doi.org/10.1038/s41597-020-0495-6).

Les données téléchargées, les secrets, les volumes et les exports déchiffrés
de cas sont exclus de Git. Le pipeline reste indépendant du matériel (ADR-16).
