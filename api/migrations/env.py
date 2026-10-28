"""Alembic : migrations du schéma du CRM MERCI (SQLite en local, Postgres en production).

L'URL vient de DATABASE_URL via app.config.settings, jamais de alembic.ini.
"""
from logging.config import fileConfig

from alembic import context
import sqlalchemy as sa
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

from app.config import settings
from app import modeles  # noqa: F401  (enregistre les tables)

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)  # garde les journaux uvicorn

target_metadata = SQLModel.metadata


def _compare_type(ctx, inspected_column, metadata_column, inspected_type, metadata_type):
    # SQLite : TEXT et VARCHAR ont la même affinité (aucune différence réelle).
    # AutoString (SQLModel) est un TypeDecorator : on compare son type sous-jacent.
    meta = getattr(metadata_type, "impl", metadata_type)
    if ctx.dialect.name == "sqlite" and isinstance(inspected_type, sa.Text) \
            and isinstance(meta, sa.String):
        return False
    return None  # comparaison par défaut d'Alembic


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # SQLite : ALTER par recopie de table
            compare_type=_compare_type,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
