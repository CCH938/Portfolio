"""Chat API routes (aiohttp) with static web UI."""

from __future__ import annotations
import time
import uuid
import os
from aiohttp import web

from app.models.schemas import ChatRequest, ChatResponse, SourceRef
from app.core.llm import generate_response, classify_intent, analyze_sentiment
from app.core.memory import ConversationMemory
from app.core.guardrails import Guardrails
from app.core.knowledge import search_knowledge

routes = web.RouteTableDef()

SYSTEM_PROMPT = """你是智能客服助手，请遵守以下规则：

1. 根据提供的知识库信息回答问题，不要编造信息
2. 如果知识库中没有相关信息，诚实告知并建议转人工
3. 保持专业、友善、有同理心的语气
4. 不确定的事情不要随意承诺
5. 遇到无法处理的问题，主动建议转人工客服

知识库参考：
{knowledge_context}

对话摘要：
{conversation_summary}"""


def _generate_suggestions(intent: str) -> list[str]:
    suggestion_map = {
        "order_query": ["查看物流详情", "修改收货地址", "申请退款"],
        "refund_request": ["查看退款进度", "联系人工客服", "重新下单"],
        "product_consult": ["查看产品规格", "对比同类商品", "咨询客服"],
        "account_service": ["修改密码", "更换绑定手机", "查看账户安全"],
        "chitchat": ["查询订单", "产品咨询", "联系客服"],
    }
    return suggestion_map.get(intent, ["查询订单", "产品咨询", "联系客服"])


@routes.post("/api/v1/chat/send")
async def send_message(request: web.Request):
    start_time = time.monotonic()
    message_id = str(uuid.uuid4())

    try:
        body = await request.json()
        req = ChatRequest(**body)
    except Exception as e:
        return web.json_response({"code": -1, "error": f"请求格式错误: {str(e)}"}, status=400)

    blocked, reason = await Guardrails.input_filter(req.content)
    if blocked:
        return web.json_response(ChatResponse(
            message_id=message_id,
            session_id=req.session_id or "blocked",
            content=reason or "抱歉，无法处理该请求。",
            intent="blocked", confidence=1.0, sentiment="neutral",
            latency_ms=int((time.monotonic() - start_time) * 1000),
            suggestions=["转人工客服"],
        ).model_dump())

    if req.session_id:
        memory = await ConversationMemory.load(req.session_id)
        if memory is None:
            memory = await ConversationMemory.create(req.user_id)
    else:
        memory = await ConversationMemory.create(req.user_id)

    intent_result = await classify_intent(req.content)
    sentiment_result = await analyze_sentiment(req.content)
    memory.update_sentiment_trend(sentiment_result.label)

    escalating = memory.is_escalating_negative()
    if sentiment_result.escalate or escalating or intent_result.intent == "human_transfer":
        content = "我已了解您的情况，正在为您转接人工客服，请稍等..."
        memory.add_turn("user", req.content, intent_result.intent, intent_result.confidence)
        memory.add_turn("assistant", content, "human_transfer", 1.0)
        return web.json_response(ChatResponse(
            message_id=message_id, session_id=memory.session_id,
            content=content, intent="human_transfer", confidence=1.0,
            sentiment=sentiment_result.label,
            latency_ms=int((time.monotonic() - start_time) * 1000),
            suggestions=[],
        ).model_dump())

    chunks = await search_knowledge(req.content)
    knowledge_context = "\n---\n".join(c.chunk_id + ": " + c.content for c in chunks) if chunks else "暂无相关知识库信息。"
    summary = memory.get_summary()
    system_prompt = SYSTEM_PROMPT.format(knowledge_context=knowledge_context, conversation_summary=summary or "新会话")
    history = memory.get_history()

    response_text = await generate_response(system_prompt=system_prompt, messages=history, user_message=req.content)

    modified, replacement = await Guardrails.output_filter(response_text)
    if modified and replacement:
        response_text = replacement

    memory.add_turn("user", req.content, intent_result.intent, intent_result.confidence)
    memory.add_turn("assistant", response_text, intent_result.intent, intent_result.confidence)

    suggestions = _generate_suggestions(intent_result.intent)
    latency = int((time.monotonic() - start_time) * 1000)
    sources = [SourceRef(doc_title=c.doc_title, chunk_id=c.chunk_id, relevance=c.relevance) for c in chunks]

    return web.json_response(ChatResponse(
        message_id=message_id, session_id=memory.session_id,
        content=response_text, intent=intent_result.intent,
        confidence=intent_result.confidence, sentiment=sentiment_result.label,
        sources=sources, latency_ms=latency, suggestions=suggestions,
    ).model_dump())


@routes.get("/api/v1/chat/history/{session_id}")
async def get_history(request: web.Request):
    session_id = request.match_info["session_id"]
    memory = await ConversationMemory.load(session_id)
    if memory is None:
        return web.json_response({"code": -1, "error": "会话不存在或已过期"}, status=404)
    history = memory.get_history()
    summary = memory.get_summary()
    return web.json_response({"session_id": session_id, "summary": summary, "turns": history})


@routes.get("/api/v1/chat/health")
async def health(request: web.Request):
    return web.json_response({"status": "ok", "service": "智能客服 Agent"})


@routes.get("/api/v1/chat/suggestions")
async def suggestions(request: web.Request):
    return web.json_response(["查询订单", "申请退款", "产品保修", "修改密码", "客服工作时间"])


# ── Static Web UI ──

@routes.get("/")
async def index(request: web.Request):
    return web.FileResponse(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "static", "index.html"))
