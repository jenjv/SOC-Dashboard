
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

engine = None
SessionLocal = None

if DATABASE_URL:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True
    )

    SessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine
    )

Base = declarative_base()


def get_db():
    if SessionLocal is None:
        raise RuntimeError("Database is not configured. Check DATABASE_URL in .env")

    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()
