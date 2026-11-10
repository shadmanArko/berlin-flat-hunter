import os
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from flathunter.core.db import DEFAULT_URL
from flathunter.core.models import Base


@pytest.fixture
def sessions() -> Iterator[sessionmaker[Session]]:
    """Isolated Postgres schema per test."""
    url = os.environ.get("DATABASE_URL", DEFAULT_URL)
    schema = f"t_{uuid.uuid4().hex[:8]}"
    admin = create_engine(url)
    try:
        with admin.begin() as c:
            c.execute(text(f"create schema {schema}"))
    except Exception as e:  # pragma: no cover
        pytest.skip(f"Postgres not available: {e}")
    eng = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    Base.metadata.create_all(eng)
    yield sessionmaker(eng, expire_on_commit=False)
    eng.dispose()
    with admin.begin() as c:
        c.execute(text(f"drop schema {schema} cascade"))
    admin.dispose()
