"""Shared pytest fixtures"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import Settings
from app.models.database import Base


@pytest.fixture
def test_settings(tmp_path):
    s = Settings(data_dir=str(tmp_path / "data"))
    s.ensure_dirs()
    return s


@pytest.fixture
def db_engine(test_settings):
    engine = create_engine(test_settings.db_url, echo=False)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    with Session(db_engine) as session:
        yield session
