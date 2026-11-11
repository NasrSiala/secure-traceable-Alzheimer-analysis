#!/usr/bin/env bash
# Audit helper: load a schema file into a throw-away PostgreSQL 16 and exercise the role grants.
# usage: verify_schema_patch.sh <schema.sql>   (prints PASS/FAIL per check, never touches other containers)
set -u
SCHEMA=$1
NAME=audit-pgcheck-$$
docker run -d --rm --name "$NAME" -e POSTGRES_HOST_AUTH_METHOD=trust postgres:16-alpine >/dev/null || exit 2
trap 'docker stop "$NAME" >/dev/null 2>&1' EXIT
for i in $(seq 1 40); do docker exec "$NAME" pg_isready -U postgres >/dev/null 2>&1 && break; sleep 1; done; sleep 2
docker exec -i "$NAME" psql -U postgres -v ON_ERROR_STOP=1 -q < "$SCHEMA" >/dev/null 2>&1 || { echo "FAIL schema does not load"; exit 1; }
q() { docker exec -i "$NAME" psql -U postgres -v ON_ERROR_STOP=1 -q -At 2>&1; }
as() { # as ROLE "sql" EXPECT(ok|deny) LABEL
  out=$(printf 'SET ROLE %s; %s' "$1" "$2" | q); rc=$?
  if [[ $3 == ok ]]; then [[ $rc -eq 0 ]] && echo "PASS $4" || { echo "FAIL $4 -> $out"; FAILS=$((FAILS+1)); }
  else echo "$out" | grep -q 'permission denied' && echo "PASS $4 (denied)" || { echo "FAIL $4 should be denied -> $out"; FAILS=$((FAILS+1)); }; fi
}
FAILS=0
U=00000000-0000-0000-0000-000000000001; C=00000000-0000-0000-0000-0000000000c1; A1=00000000-0000-0000-0000-0000000000a1; A2=00000000-0000-0000-0000-0000000000a2
as app_api "INSERT INTO users(id,email,display_name,password_hash,role) VALUES ('$U','a@b.co','Admin','\$argon2id\$x','admin');" ok "api: create user"
as app_api "UPDATE users SET locked_until=now(), last_login_at=now(), is_active=true WHERE id='$U';" ok "api: update user (lock/login)"
as app_api "INSERT INTO cases(id,created_by,ecg_format,original_sampling_hz,has_report) VALUES ('$C','$U','wfdb',500,true); INSERT INTO jobs(case_id) VALUES ('$C'); INSERT INTO audit_events(event_type) VALUES ('case_created');" ok "api: create case+job+audit"
as app_api "INSERT INTO login_attempts(email,ip,succeeded,attempted_at) VALUES ('a@b.co','127.0.0.1',false, now()-interval '40 days');" ok "api: record login attempt"
as app_api "DELETE FROM login_attempts WHERE attempted_at < now()-interval '30 days';" ok "api: purge login_attempts > 30 d (Schema 16)"
as app_api "DELETE FROM refresh_tokens WHERE expires_at < now();" ok "api: purge refresh_tokens"
as app_api "INSERT INTO validation_configs(version,conf_high,quality_min,lexicon_version) VALUES (1,0.7,0.9,'v1');" ok "api: registry.py config new"
as app_api "UPDATE validation_configs SET is_active=true WHERE version=1;" ok "api: registry.py config activate"
as app_api "UPDATE validation_configs SET conf_high=0.01 WHERE version=1;" deny "api: rewrite an existing config row"
as app_worker "SELECT id FROM jobs WHERE status='en_file' ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1;" ok "worker: claim job"
as app_worker "UPDATE jobs SET status='en_cours', locked_by='w1', heartbeat_at=now() WHERE case_id='$C'; UPDATE cases SET status='en_cours' WHERE id='$C';" ok "worker: update job/case"
as app_worker "INSERT INTO artifacts(id,case_id,type,sha256,manifest_path,offchain_ref,created_by_agent,software_version) VALUES ('$A1','$C','original',repeat('a',64),'p','artifact://$A1','ingestion','v');" ok "worker: insert artifact"
as app_worker "INSERT INTO artifacts(id,case_id,type,parent_artifact_id,sha256,manifest_path,offchain_ref,created_by_agent,software_version) VALUES ('$A2','$C','processed','$A1',repeat('b',64),'p','artifact://$A2','preparation','v');" ok "worker: insert child artifact"
as app_worker "UPDATE artifacts SET anchor_status='ancre', anchor_attempts=1, tx_id=repeat('c',64), anchored_at=now() WHERE id='$A1';" ok "worker: record anchoring"
as app_worker "UPDATE artifacts SET sha256=repeat('f',64) WHERE id='$A1';" deny "worker: rewrite artifacts.sha256"
as app_worker "INSERT INTO artifact_files(artifact_id,name,media_type,size_bytes,sha256,storage_path) VALUES ('$A1','f.enc','x',1,repeat('a',64),'/p1'); INSERT INTO agent_logs(case_id,agent,status,message,started_at,duration_ms) VALUES ('$C','ingestion','succes','m',now(),1); INSERT INTO audit_events(event_type) VALUES ('artifact_anchored');" ok "worker: files, logs, audit"
as app_worker "SELECT count(*) FROM cases; SELECT count(*) FROM artifacts; SELECT count(*) FROM models; SELECT count(*) FROM validation_configs;" ok "worker: read domain tables"
as app_worker "INSERT INTO models(name,version,framework,sha256,file_path) VALUES ('ecg-cnn1d','1.0.0','torch',repeat('a',64),'/m'); UPDATE models SET registered_tx_id=repeat('d',64), registered_at=now(), is_active=true;" ok "worker: register_model.py"
as app_worker "SELECT password_hash FROM users;" deny "worker: read users.password_hash"
as app_worker "SELECT * FROM refresh_tokens;" deny "worker: read refresh_tokens"
as app_worker "SELECT * FROM login_attempts;" deny "worker: read login_attempts"
as app_api "UPDATE models SET is_active=false;" ok "api: registry.py model activate"
as app_api "DELETE FROM cases WHERE id='$C';" ok "api: purge case (cascade over artifacts chain)"
echo "failures: $FAILS"; exit $FAILS
