"""数据库引擎管理"""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.config import settings
from app.models.database import Base

settings.ensure_dirs()
engine = create_engine(
    settings.db_url,
    echo=False,
    connect_args={"check_same_thread": False},  # SQLite 多线程支持
    pool_pre_ping=True,
)
Base.metadata.create_all(engine)

SessionLocal = sessionmaker(bind=engine)


def get_session() -> Session:
    """创建新 Session（供非 FastAPI 场景使用，如 scheduler jobs）"""
    return SessionLocal()


def get_db_dep() -> Generator[Session, None, None]:
    """FastAPI 依赖注入用的 Session 生成器

    用法:
        @app.get("/api/xxx")
        async def handler(session: Session = Depends(get_db_dep)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db():
    """Context manager 方式获取 Session

    用法:
        with get_db() as session:
            session.query(...)
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
