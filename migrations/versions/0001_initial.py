"""Schéma initial v2.0.3 : copie figée indépendante du document canonique."""

from pathlib import Path

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    script = (Path(__file__).parents[1] / "sql/0001_initial.sql").read_text(
        encoding="utf-8"
    )
    # La transaction Alembic englobe le schéma ET sa ligne de version.
    op.get_bind().execution_options(no_parameters=True).exec_driver_sql(script)


def downgrade() -> None:
    # Les rôles préexistants et leurs secrets sont conservés. Sans CASCADE :
    # un objet extérieur dépendant bloque le rollback au lieu d'être effacé.
    op.get_bind().exec_driver_sql("""
        DROP TABLE verification_items, verifications, agent_logs, audit_events,
                   artifact_files, artifacts, jobs, cases, models,
                   validation_configs, login_attempts, refresh_tokens, users;
        DROP FUNCTION set_updated_at();
        DROP TYPE user_role, case_status, decision, ecg_format, pipeline_step,
                  artifact_type, anchor_status, job_status, agent_name,
                  log_status, integrity_status, predicted_class;
        DROP SCHEMA langgraph;
    """)
