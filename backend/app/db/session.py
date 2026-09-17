"""
Async engine for Neon Postgres.

Neon computes scale to zero when idle, which can leave a pooled connection
half-dead ("SSL SYSCALL error: EOF detected"). Neon's own SQLAlchemy guide
(neon.com/docs/guides/sqlalchemy) recommends pool_pre_ping=True and/or
pool_recycle <= the scale-to-zero window — we use both, since scale-to-zero
timing isn't something this app controls.
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    settings.database_url,  # postgresql+asyncpg://... (see .env.example)
    pool_pre_ping=True,
    pool_recycle=300,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:
    """FastAPI dependency — yields a session, closes it after the request."""
    async with AsyncSessionLocal() as session:
        yield session
