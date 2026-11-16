from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from ats.settings import get_settings

config = context.config
if config.config_file_name is not None:
    # Keep the caller's loggers: tests run migrations inside the pytest process.
    fileConfig(config.config_file_name, disable_existing_loggers=False)


def database_url() -> str:
    # SQLAlchemy is only the engine for Alembic; it needs the driver named in the URL.
    url = get_settings().database_url
    return url.replace("postgresql://", "postgresql+psycopg://", 1)


def run_migrations_offline() -> None:
    context.configure(url=database_url(), literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(database_url())
    with engine.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
