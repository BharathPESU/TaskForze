"""Semantic note memory with deduplication and ranked retrieval."""

from __future__ import annotations

from typing import Any

from nexus.tools import db_tools
from nexus.tools.gemini_tools import embed_text


class SemanticMemory:
    """Thin semantic layer on top of the notes table."""

    DEDUP_THRESHOLD = 0.92

    async def add(self, content: str, user_id: str, metadata: dict[str, Any] | None = None) -> str:
        metadata = metadata or {}
        existing = await self.search(content, user_id=user_id, top_k=1)
        if existing and existing[0]["score"] >= self.DEDUP_THRESHOLD:
            await self.update(existing[0]["id"], content)
            return existing[0]["id"]

        note = await db_tools.create_note(
            {
                "title": metadata.get("title", self._title_for(content)),
                "content": content,
                "tags": metadata.get("tags", []),
                "linked_task_id": metadata.get("task_id"),
                "linked_event_id": metadata.get("event_id"),
            }
        )
        embedding = await embed_text(content)
        await db_tools.set_note_embedding(note["id"], embedding)
        return note["id"]

    async def search(self, query: str, user_id: str, top_k: int = 5) -> list[dict[str, Any]]:
        del user_id
        embedding = await embed_text(query)
        rows = await db_tools.semantic_search(embedding, top_k=top_k)
        results = []
        for row in rows:
            content = row.get("content", "")
            results.append(
                {
                    "id": row["id"],
                    "title": row.get("title") or self._title_for(content),
                    "summary": content[:120] + ("..." if len(content) > 120 else ""),
                    "score": round(float(row.get("similarity", 0.0)), 4),
                    "content": content,
                    "tags": row.get("tags", []),
                }
            )
        return results

    async def update(self, note_id: str, content: str) -> None:
        embedding = await embed_text(content)
        await db_tools.update_note(note_id, content)
        await db_tools.set_note_embedding(note_id, embedding)

    @staticmethod
    def _title_for(content: str) -> str:
        first_line = (content.strip().splitlines() or ["Untitled note"])[0]
        return first_line.lstrip("# ").strip()[:80] or "Untitled note"


memory = SemanticMemory()

