"""Database tables and the helper that opens a session.

Four tables hold everything the system knows:
  companies  one row per company found (this is the "have I seen it" memory)
  drafts     one row per message written for you to approve
  steps      one row per model call or page visit (the trace)
  lessons    short rules learned from your edits (the "style" memory)
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from functools import lru_cache

from sqlalchemy import (JSON, Boolean, DateTime, ForeignKey, Integer, String,
                        Text, UniqueConstraint, create_engine)
from sqlalchemy.orm import (DeclarativeBase, Mapped, mapped_column,
                            relationship, sessionmaker)

from .config import get_settings


def now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Company(Base):
    __tablename__ = "companies"
    __table_args__ = (UniqueConstraint("source", "source_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(20))        # "hn", "yc", "file"
    source_id: Mapped[str] = mapped_column(String(100))    # id of the post there
    name: Mapped[str] = mapped_column(String(200))
    website: Mapped[str] = mapped_column(String(500), default="")
    domain: Mapped[str] = mapped_column(String(200), default="", index=True)
    post_text: Mapped[str] = mapped_column(Text, default="")
    roles: Mapped[str] = mapped_column(String(500), default="")
    remote_policy: Mapped[str] = mapped_column(String(20), default="unclear")
    contact: Mapped[str] = mapped_column(String(200), default="")
    fit_score: Mapped[int] = mapped_column(Integer, default=0)
    fit_reason: Mapped[str] = mapped_column(Text, default="")
    # new -> drafted | failed ; or skipped straight away by the scout
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)
    note: Mapped[str] = mapped_column(Text, default="")    # why skipped / failed
    brief: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    drafts: Mapped[list["Draft"]] = relationship(back_populates="company")


class Draft(Base):
    __tablename__ = "drafts"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)                # what the agent wrote
    final_body: Mapped[str] = mapped_column(Text, default="")  # what you approved
    edited: Mapped[bool] = mapped_column(Boolean, default=False)
    verdict: Mapped[str] = mapped_column(String(20), default="")   # reviewer's verdict
    review: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    revisions: Mapped[int] = mapped_column(Integer, default=0)
    # pending -> approved -> sent ; or pending -> rejected
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    reject_reason: Mapped[str] = mapped_column(Text, default="")
    lesson_done: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                        nullable=True)

    company: Mapped[Company] = relationship(back_populates="drafts")


class Step(Base):
    __tablename__ = "steps"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(String(40), index=True)
    company_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    agent: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(80), default="")
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    ms: Mapped[int] = mapped_column(Integer, default=0)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Lesson(Base):
    __tablename__ = "lessons"

    id: Mapped[int] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    draft_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


@lru_cache
def get_engine():
    # pool_pre_ping: Neon puts an idle database to sleep; this reconnects quietly.
    return create_engine(get_settings().database_url, pool_pre_ping=True)


def init_db() -> None:
    """Create any table that does not exist yet. Safe to call on every start."""
    Base.metadata.create_all(get_engine())


@contextmanager
def session_scope():
    """Open a session, commit if the block succeeds, roll back if it fails."""
    session = sessionmaker(bind=get_engine(), expire_on_commit=False)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
