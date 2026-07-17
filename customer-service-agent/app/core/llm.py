"""LLM Gateway — unified model calling layer with streaming support."""

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from app.config import get_settings
from app.models.schemas import IntentResult, SentimentResult
import time
import json

settings = get_settings()


def _build_llm(model: str | None = None, temperature: float | None = None) -> ChatOpenAI:
    return ChatOpenAI(
        model=model or settings.llm_model,
        temperature=temperature if temperature is not None else settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        openai_api_key=settings.openai_api_key,
        openai_api_base=settings.openai_base_url,
    )


# ── Streaming Chat Completion ──

async def generate_response_stream(
    system_prompt: str,
    messages: list[dict],
    user_message: str,
    model: str | None = None,
):
    """Generate a streaming chat completion, yielding text chunks."""
    llm = _build_llm(model)
    llm.streaming = True
    
    history = [SystemMessage(content=system_prompt)]
    for m in messages[-settings.max_conversation_turns:]:
        if m["role"] == "user":
            history.append(HumanMessage(content=m["content"]))
        elif m["role"] == "assistant":
            history.append(AIMessage(content=m["content"]))
    history.append(HumanMessage(content=user_message))

    async for chunk in llm.astream(history):
        if chunk.content:
            yield chunk.content


# ── Non-streaming (kept for fallback) ──

async def generate_response(
    system_prompt: str,
    messages: list[dict],
    user_message: str,
    model: str | None = None,
) -> str:
    llm = _build_llm(model)
    history = [SystemMessage(content=system_prompt)]
    for m in messages[-settings.max_conversation_turns:]:
        if m["role"] == "user":
            history.append(HumanMessage(content=m["content"]))
        elif m["role"] == "assistant":
            history.append(AIMessage(content=m["content"]))
    history.append(HumanMessage(content=user_message))
    response = await llm.ainvoke(history)
    return response.content


# ── Intent ──

async def classify_intent(user_message: str, conversation_context: str = "") -> IntentResult:
    prompt = f"""你是一个意图分类器。将用户消息分类到以下意图之一：
- order_query: 查询订单/物流
- refund_request: 退款/退货申请
- product_consult: 产品咨询
- account_service: 账户操作
- human_transfer: 要求转人工
- chitchat: 闲聊/打招呼

对话上下文（如有）：{conversation_context}

请以 JSON 格式返回：{{"intent": "...", "confidence": 0.0-1.0, "reason": "简短理由"}}"""
    llm = _build_llm(temperature=0)
    response = await llm.ainvoke([HumanMessage(content=f"{prompt}\n\n用户消息：{user_message}")])
    try:
        data = json.loads(response.content)
        return IntentResult(intent=data["intent"], confidence=data["confidence"], method="model")
    except (json.JSONDecodeError, KeyError):
        return IntentResult(intent="chitchat", confidence=0.5, method="model")


# ── Sentiment ──

async def analyze_sentiment(user_message: str) -> SentimentResult:
    prompt = """分析用户情绪，返回 JSON：{"label": "positive|neutral|negative|angry|urgent", "score": 0.0-1.0}"""
    llm = _build_llm(temperature=0)
    response = await llm.ainvoke([HumanMessage(content=f"{prompt}\n\n用户消息：{user_message}")])
    try:
        data = json.loads(response.content)
        escalate = data["label"] in ("angry", "urgent") and data.get("score", 0) > 0.7
        return SentimentResult(label=data["label"], score=data["score"], escalate=escalate)
    except (json.JSONDecodeError, KeyError):
        return SentimentResult(label="neutral", score=0.5, escalate=False)
