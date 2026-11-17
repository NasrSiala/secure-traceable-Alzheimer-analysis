#!/usr/bin/env sh
# Créer les deux comptes de processus. Les migrations et grants sont T2.1.
set -eu

psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set ON_ERROR_STOP=1 \
    --set api_password="$APP_API_PASSWORD" --set worker_password="$APP_WORKER_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE app_api LOGIN PASSWORD %L', :'api_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_api')
\gexec
SELECT format('CREATE ROLE app_worker LOGIN PASSWORD %L', :'worker_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_worker')
\gexec
SQL
