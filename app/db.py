"""数据库引擎管理"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.config import settings
from app.models.database import Base

settings.ensure_dirs()
engine = create_engine(settings.db_url, echo=False)
Base.metadata.create_all(engine)

SessionLocal = sessionmaker(bind=engine)


def get_session() -> Session:
    return SessionLocal()
