"""Knowledge base with simple in-memory + Chroma vector store."""

from __future__ import annotations
from app.config import get_settings
from app.models.schemas import KnowledgeChunk

settings = get_settings()

# Simple in-memory store for demo / PoC
_faq_store: list[KnowledgeChunk] = []


# ── Built-in FAQ ──

def _load_builtin_faq():
    """Load built-in FAQ entries for demo purposes."""
    global _faq_store
    if _faq_store:
        return
    items = [
        ("如何查询订单状态？", "订单查询",
         "您可以在「我的订单」中输入订单号查询，或直接告诉我订单号，我来帮您查询物流状态。"),
        ("如何申请退款？", "退款退货",
         "在订单详情页点击「申请退款」，选择退款原因并提交。退款审核通过后，款项将在 3-7 个工作日内退回原支付账户。"),
        ("支持的支付方式有哪些？", "支付方式",
         "我们支持微信支付、支付宝、银行卡和 Apple Pay。部分商品还支持花呗分期和信用卡分期。"),
        ("退货运费由谁承担？", "退款退货",
         "商品质量问题导致的退换货，运费由我们承担。非质量问题的退货，运费需由您自行承担。"),
        ("产品保修多久？", "产品咨询",
         "所有电子产品享有 1 年免费保修服务，配件类产品保修期为 6 个月。保修期内非人为损坏免费维修。"),
        ("如何修改收货地址？", "账户服务",
         "订单未发货前，可在订单详情中直接修改收货地址。如已发货，请联系客服协助处理。"),
        ("忘记密码怎么办？", "账户服务",
         "在登录页面点击「忘记密码」，通过绑定的手机号或邮箱即可重置密码。"),
        ("客服工作时间是？", "常见问题",
         "在线客服工作时间为每天 9:00-22:00，智能客服 7×24 小时在线。紧急问题可拨打 400-xxx-xxxx。"),
    ]
    for i, (question, category, answer) in enumerate(items):
        _faq_store.append(KnowledgeChunk(
            chunk_id=f"faq_{i}",
            doc_title=question,
            content=f"{question}\n{answer}",
            category=category,
        ))


async def search_knowledge(query: str, top_k: int | None = None) -> list[KnowledgeChunk]:
    """Simple keyword-based search over FAQ store."""
    _load_builtin_faq()
    k = top_k or settings.retrieval_top_k
    results = []
    query_lower = query.lower()
    for chunk in _faq_store:
        # Simple TF-like scoring
        score = sum(1 for word in query_lower.split() if word in chunk.content.lower())
        score += sum(2 for word in query_lower.split() if word in chunk.doc_title.lower())
        if score > 0:
            chunk.relevance = min(score / 10.0, 1.0)
            results.append(chunk)
    results.sort(key=lambda c: c.relevance, reverse=True)
    return results[:k]


async def add_knowledge(title: str, content: str, category: str = "通用") -> KnowledgeChunk:
    """Add a new knowledge entry."""
    _load_builtin_faq()
    chunk = KnowledgeChunk(
        chunk_id=f"faq_{len(_faq_store)}",
        doc_title=title,
        content=content,
        category=category,
    )
    _faq_store.append(chunk)
    return chunk


async def delete_knowledge(chunk_id: str) -> bool:
    _load_builtin_faq()
    global _faq_store
    before = len(_faq_store)
    _faq_store = [c for c in _faq_store if c.chunk_id != chunk_id]
    return len(_faq_store) < before
