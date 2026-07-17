"""Conversation memory manager — in-memory implementation."""

from __future__ import annotations
import json
import uuid
from datetime import datetime
from app.db.database import get_store
from app.config import get_settings
from app.core.llm import _build_llm
from langchain_core.messages import HumanMessage

settings = get_settings()


class ConversationMemory:
    """Manages conversation state for a single session (in-memory)."""

    def __init__(self, session_id: str, user_id: str):
        self.store = get_store()
        self.session_id = session_id
        self.user_id = user_id

    @classmethod
    async def create(cls, user_id: str) -> "ConversationMemory":
        session_id = str(uuid.uuid4())
        memory = cls(session_id, user_id)
        memory._init_session()
        return memory

    @classmethod
    async def load(cls, session_id: str) -> "ConversationMemory | None":
        store = get_store()
        if not store.exists(f"session:{session_id}"):
            return None
        return cls(session_id, "")

    def _init_session(self):
        self.store.set(f"session:{self.session_id}", {
            "user_id": self.user_id,
            "created_at": datetime.utcnow().isoformat(),
            "turn_count": 0,
            "sentiment_trend": [],
            "summary": "",
            "status": "active",
        }, ttl=settings.session_ttl_seconds)

    def _get_meta(self) -> dict:
        return self.store.get(f"session:{self.session_id}") or {}

    def _set_meta(self, data: dict):
        self.store.set(f"session:{self.session_id}", data, ttl=settings.session_ttl_seconds)

    def add_turn(self, role: str, content: str, intent: str = "", confidence: float = 0.0):
        meta = self._get_meta()
        turns = self.store.get(f"turns:{self.session_id}") or []
        turns.append({
            "role": role,
            "content": content,
            "intent": intent,
            "confidence": confidence,
        })
        self.store.set(f"turns:{self.session_id}", turns, ttl=settings.session_ttl_seconds)
        meta["turn_count"] = len(turns)
        self._set_meta(meta)

    def get_history(self, last_n: int | None = None) -> list[dict]:
        n = last_n or settings.max_conversation_turns
        turns = self.store.get(f"turns:{self.session_id}") or []
        return turns[-n:]

    def update_sentiment_trend(self, sentiment_label: str):
        meta = self._get_meta()
        trend = meta.get("sentiment_trend", [])
        trend.append(sentiment_label)
        if len(trend) > 6:
            trend = trend[-6:]
        meta["sentiment_trend"] = trend
        self._set_meta(meta)

    def is_escalating_negative(self) -> bool:
        meta = self._get_meta()
        trend = meta.get("sentiment_trend", [])
        if len(trend) >= 3:
            negatives = sum(1 for t in trend[-3:] if t in ("negative", "angry"))
            return negatives >= 3
        return False

    def get_summary(self) -> str:
        meta = self._get_meta()
        return meta.get("summary", "")

    def close(self):
        meta = self._get_meta()
        meta["status"] = "closed"
        meta["ended_at"] = datetime.utcnow().isoformat()
        self._set_meta(meta)
