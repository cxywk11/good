from alembic import context
from jc import models  # noqa: F401
from jc.config import get_settings
from jc.db import Base
from jc.research.schema import metadata as research_metadata
from sqlalchemy import create_engine, pool

config = context.config
target_metadata = [Base.metadata, research_metadata]
url = get_settings().database_url
if context.is_offline_mode():
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    with create_engine(url, poolclass=pool.NullPool).connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()
