"""Chat API routes -- streaming SSE + function calling + admin."""

from __future__ import annotations
import time, uuid, json, os
from aiohttp import web

from app.models.schemas import ChatRequest, ChatResponse, SourceRef
from app.core.llm import generate_response_stream, generate_response, classify_intent, analyze_sentiment, _build_llm
from app.core.memory import ConversationMemory
from app.core.guardrails import Guardrails
from app.core.knowledge import search_knowledge, add_knowledge, _faq_store
from app.core.tools import TOOLS, execute_tool
from app.core.rate_limit import get_limiter
from app.db import database as db
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage

routes = web.RouteTableDef()

SYSTEM_PROMPT = """你是智能客服助手，具备以下能力：

1. 根据知识库信息回答问题，不要编造
2. 如果知识库中没有相关信息，诚实告知
3. 保持专业、友善、有同理心的语气
4. 你可以调用工具执行实际操作（查询订单、创建退款、开工单等）
5. 当用户问题信息不完整时，主动追问澄清，而不是猜测
6. 遇到无法处理的问题，主动建议转人工

知识库参考：
{knowledge_context}

对话摘要：
{conversation_summary}"""


def _generate_suggestions(intent: str) -> list[str]:
    m = {
        "order_query": ["查看物流详情", "修改收货地址", "申请退款"],
        "refund_request": ["查看退款进度", "联系人工客服", "重新下单"],
        "product_consult": ["查看产品规格", "对比同类商品", "咨询客服"],
        "account_service": ["修改密码", "更换绑定手机", "查看账户安全"],
        "chitchat": ["查询订单", "产品咨询", "联系客服"],
    }
    return m.get(intent, ["查询订单", "产品咨询", "联系客服"])


# ── 速率限制检查 ──

def _check_rate(request: web.Request, user_id: str) -> tuple[bool, str]:
    limiter = get_limiter()
    ip = request.remote or "unknown"
    key = f"{user_id}:{ip}"
    if not limiter.allow(key):
        remaining = limiter.remaining(key)
        return False, f"请求过于频繁，请稍后再试（剩余配额: {remaining}）"
    return True, ""


# ── Streaming SSE endpoint ──

@routes.post("/api/v1/chat/stream")
async def chat_stream(request: web.Request):
    start_time = time.monotonic()

    try:
        body = await request.json()
        req = ChatRequest(**body)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400)

    # Rate limit
    ok, msg = _check_rate(request, req.user_id)
    if not ok:
        return web.json_response({"error": msg}, status=429)

    blocked, reason = await Guardrails.input_filter(req.content)
    if blocked:
        return web.json_response({"error": reason}, status=400)

    if req.session_id:
        memory = await ConversationMemory.load(req.session_id)
        if memory is None:
            memory = await ConversationMemory.create(req.user_id)
    else:
        memory = await ConversationMemory.create(req.user_id)

    intent_result = await classify_intent(req.content)
    sentiment_result = await analyze_sentiment(req.content)
    await memory.update_sentiment_trend(sentiment_result.label)

    escalating = await memory.is_escalating_negative()
    if sentiment_result.escalate or escalating or intent_result.intent == "human_transfer":
        content = "我已了解您的情况，正在为您转接人工客服，请稍等..."
        await memory.add_turn("user", req.content, intent_result.intent, intent_result.confidence)
        await memory.add_turn("assistant", content, "human_transfer", 1.0)
        resp = web.StreamResponse()
        resp.headers["Content-Type"] = "text/event-stream"
        resp.headers["Cache-Control"] = "no-cache"
        await resp.prepare(request)
        await resp.write(f"data: {json.dumps({'content': content, 'done': True, 'session_id': memory.session_id, 'intent': 'human_transfer', 'confidence': 1.0, 'sentiment': sentiment_result.label, 'suggestions': []})}\n\n".encode())
        return resp

    chunks = await search_knowledge(req.content)
    knowledge_context = "\n---\n".join(c.chunk_id + ": " + c.content for c in chunks) if chunks else "暂无相关知识库信息。"
    summary = await memory.get_summary()
    system_prompt = SYSTEM_PROMPT.format(knowledge_context=knowledge_context, conversation_summary=summary or "新会话")
    history = await memory.get_history()

    resp = web.StreamResponse()
    resp.headers["Content-Type"] = "text/event-stream"
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Accel-Buffering"] = "no"
    await resp.prepare(request)

    # ── Function Calling Loop ──
    full_response = ""
    try:
        llm = _build_llm()
        llm_with_tools = llm.bind_tools(TOOLS)

        msgs = [SystemMessage(content=system_prompt)]
        for m in history[-20:]:
            if m["role"] == "user":
                msgs.append(HumanMessage(content=m["content"]))
            elif m["role"] == "assistant":
                msgs.append(AIMessage(content=m["content"]))
        msgs.append(HumanMessage(content=req.content))

        # First call
        ai_msg = await llm_with_tools.ainvoke(msgs)
        tool_calls = getattr(ai_msg, "tool_calls", None) or []

        if tool_calls:
            # Execute tools
            msgs.append(ai_msg)
            for tc in tool_calls:
                tool_name = tc.get("name", "")
                tool_args = tc.get("args", {})
                result = execute_tool(tool_name, tool_args)
                msgs.append(ToolMessage(content=json.dumps(result, ensure_ascii=False), tool_call_id=tc.get("id", "")))

            # Second call with tool results
            final_msg = await llm_with_tools.ainvoke(msgs)
            full_response = final_msg.content or ""
        else:
            full_response = ai_msg.content or ""

    except Exception:
        # Fallback: non-streaming simple completion
        full_response = await generate_response(system_prompt, history, req.content)

    # Clean up
    modified, replacement = await Guardrails.output_filter(full_response)
    if modified and replacement:
        full_response = replacement

    # Stream the response (simulate streaming for now)
    chunk_size = 8
    for i in range(0, len(full_response), chunk_size):
        chunk = full_response[i:i+chunk_size]
        await resp.write(f"data: {json.dumps({'content': chunk, 'done': False})}\n\n".encode())

    await memory.add_turn("user", req.content, intent_result.intent, intent_result.confidence)
    await memory.add_turn("assistant", full_response, intent_result.intent, intent_result.confidence)
    suggestions = _generate_suggestions(intent_result.intent)

    latency = int((time.monotonic() - start_time) * 1000)
    sources_data = [{"doc_title": c.doc_title, "chunk_id": c.chunk_id, "relevance": c.relevance} for c in chunks]

    await resp.write(f"data: {json.dumps({'content': '', 'done': True, 'session_id': memory.session_id, 'intent': intent_result.intent, 'confidence': intent_result.confidence, 'sentiment': sentiment_result.label, 'suggestions': suggestions, 'sources': sources_data, 'latency_ms': latency})}\n\n".encode())
    return resp


# ── Non-streaming ──

@routes.post("/api/v1/chat/send")
async def send_message(request: web.Request):
    start_time = time.monotonic()
    try:
        body = await request.json()
        req = ChatRequest(**body)
    except Exception as e:
        return web.json_response({"code": -1, "error": str(e)}, status=400)

    ok, msg = _check_rate(request, req.user_id)
    if not ok:
        return web.json_response({"code": -1, "error": msg}, status=429)

    blocked, reason = await Guardrails.input_filter(req.content)
    if blocked:
        return web.json_response(ChatResponse(
            message_id=str(uuid.uuid4()), session_id=req.session_id or "blocked",
            content=reason, intent="blocked", confidence=1.0,
            sentiment="neutral", latency_ms=int((time.monotonic()-start_time)*1000), suggestions=[],
        ).model_dump())

    if req.session_id:
        memory = await ConversationMemory.load(req.session_id)
        if memory is None: memory = await ConversationMemory.create(req.user_id)
    else:
        memory = await ConversationMemory.create(req.user_id)

    intent_result = await classify_intent(req.content)
    sentiment_result = await analyze_sentiment(req.content)
    await memory.update_sentiment_trend(sentiment_result.label)

    escalating = await memory.is_escalating_negative()
    if sentiment_result.escalate or escalating or intent_result.intent == "human_transfer":
        content = "我已了解您的情况，正在为您转接人工客服，请稍等..."
        await memory.add_turn("user", req.content, intent_result.intent, intent_result.confidence)
        await memory.add_turn("assistant", content, "human_transfer", 1.0)
        return web.json_response(ChatResponse(
            message_id=str(uuid.uuid4()), session_id=memory.session_id, content=content,
            intent="human_transfer", confidence=1.0, sentiment=sentiment_result.label,
            latency_ms=int((time.monotonic()-start_time)*1000), suggestions=[],
        ).model_dump())

    chunks = await search_knowledge(req.content)
    knowledge_context = "\n---\n".join(c.chunk_id+": "+c.content for c in chunks) if chunks else "暂无相关知识库信息。"
    summary = await memory.get_summary()
    system_prompt = SYSTEM_PROMPT.format(knowledge_context=knowledge_context, conversation_summary=summary or "新会话")
    history = await memory.get_history()

    # Function calling
    try:
        llm = _build_llm()
        llm_with_tools = llm.bind_tools(TOOLS)
        msgs = [SystemMessage(content=system_prompt)]
        for m in history[-20:]:
            if m["role"] == "user": msgs.append(HumanMessage(content=m["content"]))
            elif m["role"] == "assistant": msgs.append(AIMessage(content=m["content"]))
        msgs.append(HumanMessage(content=req.content))
        ai_msg = await llm_with_tools.ainvoke(msgs)
        tool_calls = getattr(ai_msg, "tool_calls", None) or []
        if tool_calls:
            msgs.append(ai_msg)
            for tc in tool_calls:
                result = execute_tool(tc.get("name",""), tc.get("args",{}))
                msgs.append(ToolMessage(content=json.dumps(result, ensure_ascii=False), tool_call_id=tc.get("id","")))
            final_msg = await llm_with_tools.ainvoke(msgs)
            response_text = final_msg.content or ""
        else:
            response_text = ai_msg.content or ""
    except Exception:
        response_text = await generate_response(system_prompt, history, req.content)

    modified, replacement = await Guardrails.output_filter(response_text)
    if modified and replacement: response_text = replacement

    await memory.add_turn("user", req.content, intent_result.intent, intent_result.confidence)
    await memory.add_turn("assistant", response_text, intent_result.intent, intent_result.confidence)

    suggestions = _generate_suggestions(intent_result.intent)
    latency = int((time.monotonic()-start_time)*1000)
    sources = [SourceRef(doc_title=c.doc_title, chunk_id=c.chunk_id, relevance=c.relevance) for c in chunks]

    return web.json_response(ChatResponse(
        message_id=str(uuid.uuid4()), session_id=memory.session_id, content=response_text,
        intent=intent_result.intent, confidence=intent_result.confidence,
        sentiment=sentiment_result.label, sources=sources, latency_ms=latency, suggestions=suggestions,
    ).model_dump())


# ── Feedback ──

@routes.post("/api/v1/chat/feedback")
async def feedback(request: web.Request):
    try:
        body = await request.json()
        db.save_feedback(body.get("session_id",""), body.get("message_index",0), body.get("rating","up"))
        return web.json_response({"status": "ok"})
    except Exception:
        return web.json_response({"status": "error"}, status=400)


@routes.get("/api/v1/chat/history/{session_id}")
async def get_history(request: web.Request):
    session_id = request.match_info["session_id"]
    memory = await ConversationMemory.load(session_id)
    if memory is None:
        return web.json_response({"code": -1, "error": "not found"}, status=404)
    history = await memory.get_history()
    summary = await memory.get_summary()
    return web.json_response({"session_id": session_id, "summary": summary, "turns": history})


@routes.get("/api/v1/chat/health")
async def health(request: web.Request):
    stats = db.get_feedback_stats()
    return web.json_response({"status": "ok", "service": "智能客服 Agent", "feedback": stats})


@routes.get("/api/v1/chat/suggestions")
async def suggestions(request: web.Request):
    return web.json_response(["查询订单 20260715001", "申请退款", "产品保修多久", "修改收货地址", "客服工作时间"])


# ── Admin: Knowledge Management ──

@routes.get("/admin")
async def admin_page(request: web.Request):
    static_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "static", "admin.html")
    return web.FileResponse(static_path)


@routes.get("/api/v1/admin/knowledge")
async def list_knowledge(request: web.Request):
    items = [{"chunk_id": c.chunk_id, "doc_title": c.doc_title, "category": c.category, "content": c.content[:100]+"..."} for c in _faq_store]
    return web.json_response({"items": items, "total": len(items)})


@routes.post("/api/v1/admin/knowledge")
async def add_knowledge_item(request: web.Request):
    try:
        body = await request.json()
        chunk = await add_knowledge(
            title=body.get("doc_title", "新条目"),
            content=body.get("content", ""),
            category=body.get("category", "通用"),
        )
        return web.json_response({"status": "ok", "chunk": {"chunk_id": chunk.chunk_id, "doc_title": chunk.doc_title}})
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=400)


@routes.delete("/api/v1/admin/knowledge/{chunk_id}")
async def delete_knowledge_item(request: web.Request):
    chunk_id = request.match_info["chunk_id"]
    global _faq_store
    idx = next((i for i, c in enumerate(_faq_store) if c.chunk_id == chunk_id), None)
    if idx is None:
        return web.json_response({"status": "error", "message": "not found"}, status=404)
    _faq_store.pop(idx)
    return web.json_response({"status": "ok"})


@routes.get("/docs")
async def docs_redirect(request: web.Request):
    raise web.HTTPFound("/")


@routes.get("/")
async def index(request: web.Request):
    static_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "static", "index.html")
    return web.FileResponse(static_path)
