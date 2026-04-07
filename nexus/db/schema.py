"""Schema helpers for PostgreSQL bootstrapping and SQLite compatibility."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

SCHEMA_SQL = """
-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Tasks
CREATE TABLE IF NOT EXISTS tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    priority INT DEFAULT 3 CHECK (priority BETWEEN 1 AND 5),
    deadline TIMESTAMPTZ,
    effort_hours FLOAT,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending','in_progress','done','blocked')),
    cognitive_load_score FLOAT,
    linked_workflow_id UUID,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

-- Task dependencies
CREATE TABLE IF NOT EXISTS task_dependencies (
    task_id UUID REFERENCES tasks(id) ON DELETE CASCADE,
    depends_on UUID REFERENCES tasks(id) ON DELETE CASCADE,
    PRIMARY KEY (task_id, depends_on)
);

-- Notes with embeddings
CREATE TABLE IF NOT EXISTS notes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT DEFAULT '',
    content TEXT NOT NULL,
    tags TEXT[],
    embedding vector(768),
    linked_task_id UUID REFERENCES tasks(id),
    linked_event_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);
CREATE INDEX IF NOT EXISTS notes_embedding_idx ON notes USING ivfflat (embedding vector_cosine_ops);

-- Workflow runs
CREATE TABLE IF NOT EXISTS workflow_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_intent TEXT DEFAULT '',
    plan JSONB DEFAULT '[]'::jsonb,
    context JSONB DEFAULT '{}'::jsonb,
    agent_outputs JSONB DEFAULT '{}'::jsonb,
    trace JSONB DEFAULT '[]'::jsonb,
    status TEXT DEFAULT 'running',
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    completed_at TIMESTAMPTZ
);

-- Active workflows
CREATE TABLE IF NOT EXISTS active_workflows (
    user_id TEXT PRIMARY KEY,
    workflow_id UUID NOT NULL,
    started_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

-- Reminder log
CREATE TABLE IF NOT EXISTS reminder_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID REFERENCES tasks(id) NOT NULL,
    channel TEXT NOT NULL CHECK (channel IN ('whatsapp','voice')),
    sent_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    acknowledged_at TIMESTAMPTZ,
    outcome TEXT CHECK (outcome IN ('ack','snoozed','escalated','no_response')),
    snooze_until TIMESTAMPTZ
);

-- User preferences
CREATE TABLE IF NOT EXISTS user_preferences (
    key TEXT PRIMARY KEY,
    value JSONB DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_deadline ON tasks(deadline);
CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority DESC);
CREATE INDEX IF NOT EXISTS idx_reminder_task ON reminder_log(task_id);
CREATE INDEX IF NOT EXISTS idx_reminder_sent ON reminder_log(sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_workflow_created ON workflow_runs(created_at DESC);
"""


async def ensure_sqlite_schema_compat(engine: AsyncEngine) -> None:
    """Patch older SQLite dev databases with newly added columns/tables."""
    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='workflow_runs'"))
        if result.scalar_one_or_none():
            column_rows = await conn.execute(text("PRAGMA table_info(workflow_runs)"))
            columns = {row[1] for row in column_rows.fetchall()}
            if "context" not in columns:
                await conn.execute(text("ALTER TABLE workflow_runs ADD COLUMN context JSON"))
            if "trace" not in columns:
                await conn.execute(text("ALTER TABLE workflow_runs ADD COLUMN trace JSON"))

        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS active_workflows (
                    user_id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )


if __name__ == "__main__":
    print(SCHEMA_SQL)
