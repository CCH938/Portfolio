"""Knowledge base with Chroma vector store + keyword fallback."""

from __future__ import annotations
import os
from app.config import get_settings
from app.models.schemas import KnowledgeChunk

settings = get_settings()

_chroma_collection = None
_faq_store: list[KnowledgeChunk] = []


def _get_faq_items() -> list[tuple[str, str, str]]:
    """(question, category, answer)"""
    return [
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
        ("发货后多久能收到？", "订单查询",
         "一般情况下，省内 1-2 天、省外 2-4 天送达。偏远地区可能需要 5-7 天。具体以物流信息为准。"),
        ("收到商品有问题怎么办？", "退款退货",
         "收到商品后 7 天内如发现质量问题，请拍照联系客服，我们会为您安排换货或退款。"),
        ("如何取消订单？", "订单查询",
         "订单未发货时可直接取消。如已发货，可在收到货后申请退货退款。"),
        ("可以货到付款吗？", "支付方式",
         "目前暂不支持货到付款，您可以选择微信支付、支付宝或银行卡在线支付。"),
    ]


def _load_builtin_faq():
    global _faq_store
    if _faq_store:
        return
    items = _get_faq_items()
    for i, (question, category, answer) in enumerate(items):
        _faq_store.append(KnowledgeChunk(
            chunk_id=f"faq_{i}",
            doc_title=question,
            content=f"{question}\n{answer}",
            category=category,
        ))


def _get_chroma_collection():
    global _chroma_collection
    if _chroma_collection is not None:
        return _chroma_collection

    try:
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        persist_dir = settings.chroma_persist_dir
        os.makedirs(persist_dir, exist_ok=True)

        client = chromadb.PersistentClient(
            path=persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        collection = client.get_or_create_collection(
            name="customer_service_faq",
            metadata={"hnsw:space": "cosine"},
        )

        # Seed if empty
        if collection.count() == 0:
            _load_builtin_faq()
            docs = [c.content for c in _faq_store]
            ids = [c.chunk_id for c in _faq_store]
            metadatas = [{"category": c.category, "title": c.doc_title} for c in _faq_store]
            collection.add(documents=docs, ids=ids, metadatas=metadatas)

        _chroma_collection = collection
        return collection
    except Exception:
        return None


async def search_knowledge(query: str, top_k: int | None = None) -> list[KnowledgeChunk]:
    k = top_k or settings.retrieval_top_k
    results = []

    # Try Chroma vector search first
    collection = _get_chroma_collection()
    if collection is not None:
        try:
            chroma_results = collection.query(query_texts=[query], n_results=k)
            if chroma_results and chroma_results.get("ids") and chroma_results["ids"][0]:
                for i, doc_id in enumerate(chroma_results["ids"][0]):
                    dist = chroma_results.get("distances", [[1.0] * k])[0][i]
                    relevance = max(0, 1.0 - dist) if dist else 0.8
                    if relevance < settings.retrieval_score_threshold:
                        continue
                    results.append(KnowledgeChunk(
                        chunk_id=doc_id,
                        doc_title=chroma_results["metadatas"][0][i].get("title", ""),
                        content=chroma_results["documents"][0][i] if chroma_results.get("documents") else "",
                        category=chroma_results["metadatas"][0][i].get("category", ""),
                        relevance=round(relevance, 3),
                    ))
        except Exception:
            pass

    # Fallback to keyword search
    if not results:
        _load_builtin_faq()
        query_lower = query.lower()
        for chunk in _faq_store:
            score = sum(1 for word in query_lower.split() if word in chunk.content.lower())
            score += sum(2 for word in query_lower.split() if word in chunk.doc_title.lower())
            if score > 0:
                chunk.relevance = min(score / 10.0, 1.0)
                results.append(chunk)
        results.sort(key=lambda c: c.relevance, reverse=True)

    return results[:k]


async def add_knowledge(title: str, content: str, category: str = "通用") -> KnowledgeChunk:
    _load_builtin_faq()
    chunk_id = f"faq_{len(_faq_store)}"
    chunk = KnowledgeChunk(chunk_id=chunk_id, doc_title=title, content=content, category=category)
    _faq_store.append(chunk)

    collection = _get_chroma_collection()
    if collection is not None:
        try:
            collection.add(documents=[content], ids=[chunk_id], metadatas=[{"category": category, "title": title}])
        except Exception:
            pass
    return chunk
