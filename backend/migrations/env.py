from logging.config import fileConfig

from alembic import context

from app import models  # noqa: F401  (registers tables on Base.metadata)
from app.config import get_settings
from app.db import Base, make_engine

target_metadata = Base.metadata

# CLI runs: log revisions and the data step's totals (alembic.ini [loggers]). Tests pass their own
# connection and keep pytest's logging.
if context.config.config_file_name and "connection" not in context.config.attributes:
    fileConfig(context.config.config_file_name, disable_existing_loggers=False)


def run_migrations_offline() -> None:
    context.configure(url=get_settings().database_url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def _run(connection) -> None:
    sqlite = connection.dialect.name == "sqlite"
    if sqlite:
        # Batch mode rebuilds tables (copy → drop → rename); with foreign keys enforced, dropping
        # a parent table would cascade-delete its children. Must be set outside a transaction.
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()  # the PRAGMA autobegins a transaction; end it so Alembic owns the next one
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=sqlite)
    with context.begin_transaction():
        context.run_migrations()
    if sqlite:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.commit()


def run_migrations_online() -> None:
    # Tests pass their own connection (config.attributes["connection"]).
    connection = context.config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return
    engine = make_engine(get_settings().database_url)
    with engine.connect() as connection:
        _run(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
