"""Pydantic models for request/response validation."""

from __future__ import annotations
from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field


# ── Request ──

class ChatRequest(BaseModel):
    platform: Literal["wecom", "dingtalk", "web"] = "web"
    user_id: str = Field(..., min_length=1, max_length=128, description="用户唯一标识")
    session_id: Optional[str] = Field(None, description="会话 ID，为空则创建新会话")
    content: str = Field(..., min_length=1, max_length=4000, description="用户消息")
    content_type: Literal["text", "image", "voice", "file"] = "text"


# ── Response ──

class SourceRef(BaseModel):
    doc_title: str
    chunk_id: str
    relevance: float


class ChatResponse(BaseModel):
    message_id: str
    session_id: str
    content: str
    intent: Optional[str] = None
    confidence: Optional[float] = None
    sentiment: Optional[str] = None
    sources: list[SourceRef] = []
    latency_ms: int
    suggestions: list[str] = []


# ── Internal ──

class UnifiedMessage(BaseModel):
    platform: str
    user_id: str
    session_id: str
    content_type: str = "text"
    content: str
    raw_payload: dict = {}
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ConversationTurn(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str
    intent: Optional[str] = None
    confidence: Optional[float] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class IntentResult(BaseModel):
    intent: str
    confidence: float
    slots: dict = {}
    method: Literal["rule", "model", "llm"] = "model"


class SentimentResult(BaseModel):
    label: Literal["positive", "neutral", "negative", "angry", "urgent"]
    score: float
    escalate: bool = False


class KnowledgeChunk(BaseModel):
    chunk_id: str
    doc_title: str
    content: str
    category: Optional[str] = None
    relevance: float = 0.0
