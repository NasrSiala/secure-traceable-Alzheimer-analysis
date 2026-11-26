-- SAAMSTIAHF — schéma PostgreSQL 16 (Backend Schema v2.0.3, suite v2.1.4, 2026-11-09 — tables, colonnes et contraintes inchangées depuis la v1.0.0 ; privilèges resserrés)
-- Source de vérité : docs/specs/04-backend-schema.md. Les migrations Alembic doivent reproduire ce fichier.
-- Les tables de checkpoint LangGraph sont créées par langgraph-checkpoint-postgres dans le schéma `langgraph`.


CREATE SCHEMA IF NOT EXISTS langgraph;

-- ---------------------------------------------------------------- Enums
CREATE TYPE user_role         AS ENUM ('operator', 'auditor', 'admin');
CREATE TYPE case_status       AS ENUM ('en_attente', 'en_cours', 'termine', 'erreur_ancrage', 'erreur');
CREATE TYPE decision          AS ENUM ('accepte', 'revision_requise', 'rejete');
CREATE TYPE ecg_format        AS ENUM ('wfdb', 'csv');
CREATE TYPE pipeline_step     AS ENUM ('ingestion', 'preparation', 'features', 'prediction',
                                       'validation', 'explanation', 'finalization');
CREATE TYPE artifact_type     AS ENUM ('original', 'processed', 'features', 'prediction',
                                       'validation', 'explanation', 'final_result');
CREATE TYPE anchor_status     AS ENUM ('en_attente', 'ancre', 'echec');
CREATE TYPE job_status        AS ENUM ('en_file', 'en_cours', 'termine', 'echec');
CREATE TYPE agent_name        AS ENUM ('orchestrator', 'ingestion', 'preparation', 'features', 'prediction',
                                       'validation', 'explanation', 'finalization', 'verifier');
CREATE TYPE log_status        AS ENUM ('succes', 'echec', 'ignore');
CREATE TYPE integrity_status  AS ENUM ('valide', 'modifie', 'manquant', 'non_verifiable');
CREATE TYPE predicted_class   AS ENUM ('NORM', 'MI', 'STTC', 'CD', 'HYP');

-- ---------------------------------------------------------------- updated_at trigger
CREATE FUNCTION set_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at := now(); RETURN NEW; END $$;

-- ---------------------------------------------------------------- users
CREATE TABLE users (
  id             uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  email          text        NOT NULL CHECK (length(email) <= 254 AND email = lower(email) AND email ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$'),
  display_name   text        NOT NULL CHECK (length(display_name) BETWEEN 1 AND 100),
  password_hash  text        NOT NULL CHECK (password_hash LIKE '$argon2id$%'),
  role           user_role   NOT NULL,
  is_active      boolean     NOT NULL DEFAULT true,
  locked_until   timestamptz,
  last_login_at  timestamptz,
  created_by     uuid        REFERENCES users(id) ON DELETE SET NULL,
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_users_email ON users (email);
CREATE TRIGGER trg_users_updated BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------- refresh_tokens
CREATE TABLE refresh_tokens (
  id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash  char(64)    NOT NULL UNIQUE CHECK (token_hash ~ '^[0-9a-f]{64}$'),
  expires_at  timestamptz NOT NULL,
  revoked_at  timestamptz,
  user_agent  text        CHECK (length(user_agent) <= 300),
  created_at  timestamptz NOT NULL DEFAULT now(),
  CHECK (expires_at > created_at)
);
CREATE INDEX idx_refresh_tokens_user ON refresh_tokens (user_id) WHERE revoked_at IS NULL;

-- ---------------------------------------------------------------- login_attempts
CREATE TABLE login_attempts (
  id            bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  email         text        NOT NULL CHECK (email = lower(email) AND length(email) <= 254),
  ip            inet        NOT NULL,
  succeeded     boolean     NOT NULL,
  attempted_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_login_attempts_email_time ON login_attempts (email, attempted_at DESC);

-- ---------------------------------------------------------------- validation_configs
CREATE TABLE validation_configs (
  id               uuid         PRIMARY KEY DEFAULT gen_random_uuid(),
  version          integer      NOT NULL UNIQUE CHECK (version > 0),
  conf_high        numeric(4,3) NOT NULL CHECK (conf_high > 0 AND conf_high <= 1),
  quality_min      numeric(4,3) NOT NULL CHECK (quality_min > 0 AND quality_min <= 1),
  lexicon_version  text         NOT NULL CHECK (length(lexicon_version) <= 40),
  is_active        boolean      NOT NULL DEFAULT false,
  created_by       uuid         REFERENCES users(id) ON DELETE SET NULL,
  created_at       timestamptz  NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_validation_configs_active ON validation_configs (is_active) WHERE is_active;

-- ---------------------------------------------------------------- models
CREATE TABLE models (
  id                uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  name              text        NOT NULL CHECK (name ~ '^[a-z0-9_-]{1,60}$'),
  version           text        NOT NULL CHECK (version ~ '^[0-9]+\.[0-9]+\.[0-9]+$'),
  framework         text        NOT NULL CHECK (length(framework) <= 40),
  sha256            char(64)    NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  file_path         text        NOT NULL CHECK (length(file_path) <= 300),
  metrics           jsonb       NOT NULL DEFAULT '{}'::jsonb,
  is_active         boolean     NOT NULL DEFAULT false,
  registered_tx_id  text        CHECK (registered_tx_id ~ '^[0-9a-f]{64}$'),
  registered_at     timestamptz,
  created_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (name, version),
  CHECK (NOT is_active OR registered_tx_id IS NOT NULL)
);
CREATE UNIQUE INDEX uq_models_active ON models (is_active) WHERE is_active;

-- ---------------------------------------------------------------- cases
CREATE TABLE cases (
  id                    uuid           PRIMARY KEY DEFAULT gen_random_uuid(),
  case_ref              text           GENERATED ALWAYS AS ('CASE-' || id::text) STORED UNIQUE,
  created_by            uuid           NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  status                case_status    NOT NULL DEFAULT 'en_attente',
  current_step          pipeline_step,
  ecg_format            ecg_format     NOT NULL,
  original_sampling_hz  integer        NOT NULL CHECK (original_sampling_hz BETWEEN 50 AND 10000),
  has_report            boolean        NOT NULL,
  model_id              uuid           REFERENCES models(id) ON DELETE RESTRICT,
  validation_config_id  uuid           REFERENCES validation_configs(id) ON DELETE RESTRICT,
  -- dénormalisé depuis les artefacts pour les listes (§13)
  quality_score         numeric(5,4)   CHECK (quality_score BETWEEN 0 AND 1),
  predicted_class       predicted_class,
  confidence            numeric(5,4)   CHECK (confidence BETWEEN 0 AND 1),
  decision              decision,
  error_message         text           CHECK (length(error_message) <= 1000),
  completed_at          timestamptz,
  created_at            timestamptz    NOT NULL DEFAULT now(),
  updated_at            timestamptz    NOT NULL DEFAULT now(),
  CHECK ((status = 'termine') = (decision IS NOT NULL)),
  CHECK ((status IN ('termine', 'erreur_ancrage', 'erreur')) = (completed_at IS NOT NULL))
);
CREATE TRIGGER trg_cases_updated BEFORE UPDATE ON cases FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE INDEX idx_cases_created_at ON cases (created_at DESC);
CREATE INDEX idx_cases_status ON cases (status);
CREATE INDEX idx_cases_created_by ON cases (created_by);

-- ---------------------------------------------------------------- artifacts
CREATE TABLE artifacts (
  id                  uuid          PRIMARY KEY,               -- généré par l'agent AVANT l'ancrage (TRD §22)
  case_id             uuid          NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  type                artifact_type NOT NULL,
  parent_artifact_id  uuid          REFERENCES artifacts(id) ON DELETE RESTRICT,
  sha256              char(64)      NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),  -- copie d'affichage ; la vérif lit Fabric
  manifest_path       text          NOT NULL CHECK (length(manifest_path) <= 300),
  offchain_ref        text          NOT NULL CHECK (offchain_ref = 'artifact://' || id::text),
  created_by_agent    agent_name    NOT NULL,
  software_version    text          NOT NULL CHECK (length(software_version) <= 64),
  model_version       text          CHECK (length(model_version) <= 64),
  anchor_status       anchor_status NOT NULL DEFAULT 'en_attente',
  anchor_attempts     smallint      NOT NULL DEFAULT 0 CHECK (anchor_attempts BETWEEN 0 AND 4),  -- 1 tentative + 3 réessais (AC-07.4)
  tx_id               text          CHECK (tx_id ~ '^[0-9a-f]{64}$'),
  anchored_at         timestamptz,
  created_at          timestamptz   NOT NULL DEFAULT now(),
  UNIQUE (case_id, type),
  CHECK ((type = 'original') = (parent_artifact_id IS NULL)),
  CHECK ((anchor_status = 'ancre') = (tx_id IS NOT NULL AND anchored_at IS NOT NULL)),
  CHECK (created_by_agent <> 'verifier' AND created_by_agent <> 'orchestrator')
);
CREATE INDEX idx_artifacts_parent ON artifacts (parent_artifact_id);

-- ---------------------------------------------------------------- artifact_files
CREATE TABLE artifact_files (
  id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  artifact_id   uuid        NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
  name          text        NOT NULL CHECK (name ~ '^[A-Za-z0-9._-]{1,100}$'),
  media_type    text        NOT NULL CHECK (length(media_type) <= 100),
  size_bytes    bigint      NOT NULL CHECK (size_bytes BETWEEN 0 AND 20971520),
  sha256        char(64)    NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  storage_path  text        NOT NULL UNIQUE CHECK (length(storage_path) <= 300),
  created_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (artifact_id, name)
);

-- ---------------------------------------------------------------- jobs
CREATE TABLE jobs (
  id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  case_id       uuid        NOT NULL UNIQUE REFERENCES cases(id) ON DELETE CASCADE,
  status        job_status  NOT NULL DEFAULT 'en_file',
  attempts      smallint    NOT NULL DEFAULT 0 CHECK (attempts >= 0),
  max_attempts  smallint    NOT NULL DEFAULT 3 CHECK (max_attempts BETWEEN 1 AND 10),
  locked_by     text        CHECK (length(locked_by) <= 100),
  locked_at     timestamptz,
  heartbeat_at  timestamptz,
  last_error    text        CHECK (length(last_error) <= 2000),
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now(),
  CHECK (attempts <= max_attempts),
  CHECK ((status = 'en_cours') = (locked_by IS NOT NULL))
);
CREATE TRIGGER trg_jobs_updated BEFORE UPDATE ON jobs FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE INDEX idx_jobs_queue ON jobs (created_at) WHERE status = 'en_file';
CREATE INDEX idx_jobs_running_heartbeat ON jobs (heartbeat_at) WHERE status = 'en_cours';

-- ---------------------------------------------------------------- agent_logs
CREATE TABLE agent_logs (
  id                  bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  case_id             uuid        NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  job_id              uuid        REFERENCES jobs(id) ON DELETE SET NULL,
  agent               agent_name  NOT NULL,
  step                pipeline_step,
  status              log_status  NOT NULL,
  input_artifact_ids  uuid[]      NOT NULL DEFAULT '{}',
  output_artifact_id  uuid        REFERENCES artifacts(id) ON DELETE SET NULL,
  message             text        NOT NULL CHECK (length(message) <= 1000),
  details             jsonb       NOT NULL DEFAULT '{}'::jsonb,
  started_at          timestamptz NOT NULL,
  duration_ms         integer     NOT NULL CHECK (duration_ms >= 0),
  created_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_agent_logs_case_time ON agent_logs (case_id, started_at);

-- ---------------------------------------------------------------- verifications
CREATE TABLE verifications (
  id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  case_id             uuid        NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  requested_by        uuid        NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  ledger_reachable    boolean     NOT NULL,
  count_valide        smallint    NOT NULL DEFAULT 0 CHECK (count_valide >= 0),
  count_modifie       smallint    NOT NULL DEFAULT 0 CHECK (count_modifie >= 0),
  count_manquant      smallint    NOT NULL DEFAULT 0 CHECK (count_manquant >= 0),
  count_non_verifiable smallint   NOT NULL DEFAULT 0 CHECK (count_non_verifiable >= 0),
  started_at          timestamptz NOT NULL,
  completed_at        timestamptz NOT NULL,
  created_at          timestamptz NOT NULL DEFAULT now(),
  CHECK (completed_at >= started_at)
);
CREATE INDEX idx_verifications_case_time ON verifications (case_id, completed_at DESC);

-- ---------------------------------------------------------------- verification_items
CREATE TABLE verification_items (
  id               uuid             PRIMARY KEY DEFAULT gen_random_uuid(),
  verification_id  uuid             NOT NULL REFERENCES verifications(id) ON DELETE CASCADE,
  artifact_id      uuid             NOT NULL,   -- pas de FK : peut désigner un artefact présent on-chain seulement
  artifact_type    artifact_type    NOT NULL,
  status           integrity_status NOT NULL,
  expected_sha256  char(64)         CHECK (expected_sha256 ~ '^[0-9a-f]{64}$'),   -- lu sur Fabric
  computed_sha256  char(64)         CHECK (computed_sha256 ~ '^[0-9a-f]{64}$'),   -- recalculé hors chaîne
  detail           text             CHECK (length(detail) <= 500),
  UNIQUE (verification_id, artifact_id),
  CHECK (status <> 'valide'         OR (expected_sha256 IS NOT NULL AND expected_sha256 = computed_sha256)),
  CHECK (status <> 'non_verifiable' OR expected_sha256 IS NULL)
);

-- ---------------------------------------------------------------- audit_events
CREATE TABLE audit_events (
  id             bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  event_type     text        NOT NULL CHECK (event_type ~ '^[a-z_]{3,60}$'),
  actor_user_id  uuid        REFERENCES users(id) ON DELETE SET NULL,
  case_id        uuid        REFERENCES cases(id) ON DELETE SET NULL,
  payload        jsonb       NOT NULL DEFAULT '{}'::jsonb,
  created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_events_type_time ON audit_events (event_type, created_at DESC);
CREATE INDEX idx_audit_events_case ON audit_events (case_id) WHERE case_id IS NOT NULL;

-- ---------------------------------------------------------------- rôles de base de données (défense en profondeur)
-- Les mots de passe sont définis hors de ce fichier (secrets Docker).
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_api')    THEN CREATE ROLE app_api    LOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_worker') THEN CREATE ROLE app_worker LOGIN; END IF;
END $$;

GRANT USAGE ON SCHEMA public TO app_api, app_worker;
GRANT USAGE, CREATE ON SCHEMA langgraph TO app_worker;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO app_api, app_worker;
-- le worker ne lit ni les comptes, ni les jetons de rafraîchissement, ni les tentatives de connexion
REVOKE SELECT ON users, refresh_tokens, login_attempts FROM app_worker;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO app_api, app_worker;

-- api : authentification, création de cas, vérifications, administration, audit
GRANT INSERT, UPDATE         ON users                               TO app_api;
GRANT INSERT                 ON validation_configs                  TO app_api;   -- lignes jamais modifiées (Schema §5.1)
GRANT UPDATE (is_active)     ON validation_configs                  TO app_api;   -- scripts/registry.py config activate
GRANT INSERT, UPDATE, DELETE ON refresh_tokens                      TO app_api;
GRANT INSERT                 ON login_attempts, cases, jobs,
                                verifications, verification_items,
                                audit_events                        TO app_api;
GRANT UPDATE (is_active)     ON models                              TO app_api;
GRANT DELETE                 ON cases                               TO app_api;   -- purge admin (cascade)
GRANT DELETE                 ON login_attempts                      TO app_api;   -- rétention 30 jours (Schema §16)

-- worker : exécution du pipeline
GRANT UPDATE                 ON cases, jobs                         TO app_worker;
GRANT INSERT                 ON artifacts                           TO app_worker;
GRANT UPDATE (anchor_status, anchor_attempts, tx_id, anchored_at)
                             ON artifacts                           TO app_worker;   -- sha256, type, parent jamais modifiés (Schema §10)
GRANT INSERT                 ON artifact_files, agent_logs,
                                audit_events                        TO app_worker;
GRANT INSERT, UPDATE         ON models                              TO app_worker; -- scripts/register_model.py
