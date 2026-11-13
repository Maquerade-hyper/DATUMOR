import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.engine import URL

ROOT = Path(__file__).resolve().parents[3]
load_dotenv(ROOT / ".env")

DATABASE_URL = URL.create(
    "postgresql+psycopg",
    username=os.environ["DATUMOR_DB_USER"],
    password=os.environ["DATUMOR_DB_PASSWORD"],
    host=os.getenv("DATUMOR_DB_HOST", "127.0.0.1"),
    port=int(os.getenv("DATUMOR_DB_PORT", "5432")),
    database=os.environ["DATUMOR_DB_NAME"],
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


def initialize_database():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
