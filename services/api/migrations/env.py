import app.models.community  # register community metadata
import app.models.statistics  # register statistics metadata
import os
from alembic import context
from sqlalchemy import create_engine
from app.models.database import Base

config = context.config


def run():
    url = os.getenv("DATABASE_URL", config.get_main_option("sqlalchemy.url"))
    if context.is_offline_mode():
        context.configure(url=url, target_metadata=Base.metadata, literal_binds=True)
        with context.begin_transaction():
            context.run_migrations()
    else:
        with create_engine(url).connect() as connection:
            context.configure(connection=connection, target_metadata=Base.metadata)
            with context.begin_transaction():
                context.run_migrations()


run()
