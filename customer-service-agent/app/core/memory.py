"""Conversation memory manager — SQLite-backed with auto-summarization."""

from __future__ import annotations
import uuid
from app.config import get_settings
from app.core.llm import _build_llm
from app.db import database as db
from langchain_core.messages import HumanMessage

settings = get_settings()


class ConversationMemory:
    """Manages conversation state for a single session (SQLite)."""

    def __init__(self, session_id: str, user_id: str = ""):
        self.session_id = session_id
        self.user_id = user_id

    @classmethod
    async def create(cls, user_id: str) -> "ConversationMemory":
        session_id = str(uuid.uuid4())
        db.create_session(session_id, user_id)
        return cls(session_id, user_id)

    @classmethod
    async def load(cls, session_id: str) -> "ConversationMemory | None":
        if not db.session_exists(session_id):
            return None
        return cls(session_id)

    async def add_turn(self, role: str, content: str, intent: str = "", confidence: float = 0.0):
        db.add_message_db(self.session_id, role, content, intent, confidence)

    async def get_history(self, last_n: int | None = None) -> list[dict]:
        n = last_n or settings.max_conversation_turns
        return db.get_messages(self.session_id, n)

    async def update_sentiment_trend(self, sentiment_label: str):
        trend = db.get_session_trend(self.session_id)
        trend.append(sentiment_label)
        if len(trend) > 6:
            trend = trend[-6:]
        db.update_session_trend(self.session_id, trend)

    async def is_escalating_negative(self) -> bool:
        trend = db.get_session_trend(self.session_id)
        if len(trend) >= 3:
            negatives = sum(1 for t in trend[-3:] if t in ("negative", "angry"))
            return negatives >= 3
        return False

    async def get_summary(self) -> str:
        return db.get_session_summary(self.session_id)

    async def summarize_and_compress(self):
        history = await self.get_history()
        if len(history) <= settings.summary_trigger_turns:
            return
        llm = _build_llm(temperature=0)
        conv_text = "\n".join(f"{t['role']}: {t['content']}" for t in history)
        response = await llm.ainvoke([
            HumanMessage(content=f"请用一两句话总结以下对话的关键信息：\n{conv_text}")
        ])
        db.update_session_summary(self.session_id, response.content)

    async def close(self):
        db.close_session(self.session_id)
