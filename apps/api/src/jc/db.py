from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from jc.config import get_settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str):
    options = {"check_same_thread": False} if url.startswith("sqlite") else {"options": "-c timezone=UTC"}
    result = create_engine(url, pool_pre_ping=True, connect_args=options)
    if url.startswith("sqlite"):

        @event.listens_for(result, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

    return result


engine = make_engine(get_settings().database_url)
SessionLocal = sessionmaker(engine, expire_on_commit=False)

# Install post-commit visibility proofs for immutable analysis inputs (Core connection, no recursion).
from jc.analysis import visibility as _visibility  # noqa: E402,F401


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session
