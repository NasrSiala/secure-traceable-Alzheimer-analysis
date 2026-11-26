"""Migrations administratives : connexion distincte des rôles applicatifs."""

import os

from alembic import context
from sqlalchemy import create_engine, pool


def run() -> None:
    supplied = context.config.attributes.get("connection")
    if supplied is not None:
        context.configure(connection=supplied, transactional_ddl=True)
        with context.begin_transaction():
            context.run_migrations()
        return
    url = os.environ.get("DATABASE_URL_MIGRATIONS", "")
    if not url:
        raise RuntimeError(
            "DATABASE_URL_MIGRATIONS doit désigner le compte de migration."
        )
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    if context.is_offline_mode():
        context.configure(url=url, literal_binds=True, transactional_ddl=True)
        with context.begin_transaction():
            context.run_migrations()
    else:
        engine = create_engine(url, poolclass=pool.NullPool, hide_parameters=True)
        with engine.connect() as connection:
            context.configure(connection=connection, transactional_ddl=True)
            with context.begin_transaction():
                context.run_migrations()
        engine.dispose()


run()
