"""SQLAlchemy ORM models — PostgreSQL + pgvector (with SQLite dev fallback)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    event,
)
from sqlalchemy.orm import DeclarativeBase, relationship

from nexus.config import settings

_is_sqlite = settings.database_url.startswith("sqlite")

# ── Conditional type imports ──────────────────────────────────────────
if _is_sqlite:
    # SQLite fallback — no pgvector, no UUID type, no ARRAY
    _UUID = String(36)
    _JSONB = JSON
    _ARRAY_Text = JSON  # store as JSON array
    _Vector = lambda dim: Text  # store embedding as JSON string
    _server_now = None  # handle in Python
else:
    from pgvector.sqlalchemy import Vector as _PgVector
    from sqlalchemy.dialects.postgresql import JSONB as _PgJSONB, UUID as _PgUUID, ARRAY as _PgARRAY

    _UUID = _PgUUID(as_uuid=True)
    _JSONB = _PgJSONB
    _ARRAY_Text = _PgARRAY(Text)
    _Vector = lambda dim: _PgVector(dim)
    _server_now = None  # use Python default for consistency


def _utcnow():
    return datetime.now(timezone.utc)


def _uuid():
    return uuid.uuid4() if not _is_sqlite else str(uuid.uuid4())


class Base(DeclarativeBase):
    """Shared declarative base for all models."""


# ── Tasks ─────────────────────────────────────────────────────────────
class Task(Base):
    __tablename__ = "tasks"

    id = Column(_UUID, primary_key=True, default=_uuid)
    title = Column(Text, nullable=False)
    description = Column(Text, default="")
    priority = Column(Integer, default=3)
    deadline = Column(DateTime(timezone=True), nullable=True)
    effort_hours = Column(Float, nullable=True)
    status = Column(String(20), default="pending", nullable=False)
    cognitive_load_score = Column(Float, nullable=True)
    linked_workflow_id = Column(_UUID, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    # relationships
    reminders = relationship("ReminderLog", back_populates="task", lazy="selectin")
    notes = relationship("Note", back_populates="task", lazy="selectin")


# ── Task Dependencies ─────────────────────────────────────────────────
class TaskDependency(Base):
    __tablename__ = "task_dependencies"

    task_id = Column(
        _UUID, ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    depends_on = Column(
        _UUID, ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )


# ── Notes ─────────────────────────────────────────────────────────────
class Note(Base):
    __tablename__ = "notes"

    id = Column(_UUID, primary_key=True, default=_uuid)
    title = Column(Text, default="")
    content = Column(Text, nullable=False)
    tags = Column(_ARRAY_Text if not _is_sqlite else JSON, default=list)
    embedding = Column(_Vector(768), nullable=True)
    linked_task_id = Column(_UUID, ForeignKey("tasks.id"), nullable=True)
    linked_event_id = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    task = relationship("Task", back_populates="notes")


# ── Workflow Runs ─────────────────────────────────────────────────────
class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id = Column(_UUID, primary_key=True, default=_uuid)
    user_intent = Column(Text, default="")
    plan = Column(_JSONB if not _is_sqlite else JSON, default=list)
    context = Column(_JSONB if not _is_sqlite else JSON, default=dict)
    agent_outputs = Column(_JSONB if not _is_sqlite else JSON, default=dict)
    trace = Column(_JSONB if not _is_sqlite else JSON, default=list)
    status = Column(String(20), default="running")
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)


# ── Active Workflows ─────────────────────────────────────────────────
class ActiveWorkflow(Base):
    __tablename__ = "active_workflows"

    user_id = Column(Text, primary_key=True)
    workflow_id = Column(_UUID, nullable=False)
    started_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)


# ── Reminder Log ──────────────────────────────────────────────────────
class ReminderLog(Base):
    __tablename__ = "reminder_log"

    id = Column(_UUID, primary_key=True, default=_uuid)
    task_id = Column(_UUID, ForeignKey("tasks.id"), nullable=False)
    channel = Column(String(20), nullable=False)
    sent_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    outcome = Column(String(20), nullable=True)
    snooze_until = Column(DateTime(timezone=True), nullable=True)

    task = relationship("Task", back_populates="reminders")


# ── User Preferences ─────────────────────────────────────────────────
class UserPreference(Base):
    __tablename__ = "user_preferences"

    key = Column(Text, primary_key=True)
    value = Column(_JSONB if not _is_sqlite else JSON, default=dict)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
