from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
    JSON
)

from sqlalchemy.sql import func

from .database import Base


class Event(Base):

    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)

    event_id = Column(String(100), unique=True, nullable=False)

    timestamp = Column(DateTime(timezone=True), nullable=False)

    source_machine = Column(String(100), nullable=False)

    event_type = Column(String(100), nullable=False)

    severity = Column(String(20), nullable=False)

    source_ip = Column(String(100), nullable=True)

    destination_ip = Column(String(100), nullable=True)

    username = Column(String(255), nullable=True)

    description = Column(Text, nullable=False)

    status = Column(String(30), default="new")

    raw_log = Column(JSON, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )


class Alert(Base):

    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)

    rule_id = Column(String(100), nullable=False)

    title = Column(String(255), nullable=False)

    severity = Column(String(20), nullable=False)

    description = Column(Text, nullable=False)

    source_machine = Column(String(100), nullable=False)

    source_ip = Column(String(100), nullable=True)

    event_id = Column(
        String(100),
        ForeignKey("events.event_id", ondelete="SET NULL"),
        nullable=True
    )

    status = Column(String(30), default="new")

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )
