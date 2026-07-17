"""Function Calling tools — mock order/CRM system."""

from __future__ import annotations
import json
import uuid
from datetime import datetime, timedelta

# ── Mock Data ──

_orders = {
    "20260715001": {"status": "运输中", "courier": "顺丰", "tracking": "SF1234567890", "eta": "2026-07-18", "items": "无线蓝牙耳机 ×1", "amount": 299},
    "20260710002": {"status": "已签收", "courier": "圆通", "tracking": "YT9876543210", "eta": None, "items": "智能手表 ×1", "amount": 899},
    "20260708003": {"status": "待发货", "courier": None, "tracking": None, "eta": "2026-07-19", "items": "手机壳 ×2", "amount": 58},
    "20260705004": {"status": "退款中", "courier": "中通", "tracking": "ZT1111222233", "eta": None, "items": "运动鞋 ×1", "amount": 399},
}

_tickets = {}
_returns = {}

# ── Tool Definitions (OpenAI function calling format) ──

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "query_order",
            "description": "查询用户的订单状态、物流信息。当用户询问订单、快递、物流时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "订单号，如 20260715001"},
                },
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_refund",
            "description": "为用户创建退款/退货申请。当用户明确要求退款或退货时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "订单号"},
                    "reason": {"type": "string", "description": "退款原因"},
                },
                "required": ["order_id", "reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_ticket",
            "description": "创建人工客服工单。当需要转人工、问题无法自动解决时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "用户ID"},
                    "summary": {"type": "string", "description": "问题摘要"},
                    "priority": {"type": "string", "enum": ["low", "normal", "high", "urgent"], "description": "优先级"},
                },
                "required": ["user_id", "summary", "priority"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_warranty",
            "description": "查询产品保修状态和政策。",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_type": {"type": "string", "description": "产品类型，如 电子产品、配件、家电"},
                },
                "required": ["product_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "modify_address",
            "description": "修改订单收货地址（仅未发货订单）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "订单号"},
                    "new_address": {"type": "string", "description": "新收货地址"},
                },
                "required": ["order_id", "new_address"],
            },
        },
    },
]


# ── Tool Implementations ──

def execute_tool(name: str, arguments: dict) -> dict:
    """Execute a tool call and return the result."""
    handlers = {
        "query_order": _query_order,
        "request_refund": _request_refund,
        "create_ticket": _create_ticket,
        "check_warranty": _check_warranty,
        "modify_address": _modify_address,
    }
    handler = handlers.get(name)
    if handler:
        return handler(**arguments)
    return {"error": f"Unknown tool: {name}"}


def _query_order(order_id: str) -> dict:
    order = _orders.get(order_id)
    if not order:
        return {"found": False, "message": f"未找到订单 {order_id}，请核对订单号"}
    return {"found": True, **order}


def _request_refund(order_id: str, reason: str) -> dict:
    order = _orders.get(order_id)
    if not order:
        return {"success": False, "message": f"订单 {order_id} 不存在"}
    if order["status"] in ("退款中", "已退款"):
        return {"success": False, "message": f"订单 {order_id} 已在退款流程中"}
    refund_id = str(uuid.uuid4())[:8]
    _returns[refund_id] = {"order_id": order_id, "reason": reason, "status": "处理中", "created_at": datetime.utcnow().isoformat()}
    return {"success": True, "refund_id": refund_id, "message": f"退款申请已提交，退款编号 {refund_id}，预计 3-7 个工作日到账"}


def _create_ticket(user_id: str, summary: str, priority: str) -> dict:
    ticket_id = "TK" + str(uuid.uuid4())[:8].upper()
    _tickets[ticket_id] = {"user_id": user_id, "summary": summary, "priority": priority, "status": "待处理", "created_at": datetime.utcnow().isoformat()}
    return {"success": True, "ticket_id": ticket_id, "message": f"工单 {ticket_id} 已创建，优先级 {priority}，客服将尽快处理"}


def _check_warranty(product_type: str) -> dict:
    policies = {
        "电子产品": {"period": "1年", "coverage": "非人为损坏免费维修", "note": "需保留购买凭证"},
        "配件": {"period": "6个月", "coverage": "非人为损坏免费更换", "note": "不含外观磨损"},
        "家电": {"period": "2年", "coverage": "主要部件免费维修", "note": "易损件保修3个月"},
    }
    pt = product_type.strip()
    if pt in policies:
        return {"found": True, "product_type": pt, **policies[pt]}
    return {"found": True, "product_type": pt, "period": "请提供具体产品型号", "coverage": "不同产品保修政策不同", "note": "可联系人工客服查询详细政策"}


def _modify_address(order_id: str, new_address: str) -> dict:
    order = _orders.get(order_id)
    if not order:
        return {"success": False, "message": f"订单 {order_id} 不存在"}
    if order["status"] != "待发货":
        return {"success": False, "message": f"订单状态为「{order['status']}」，无法修改地址。建议收货后申请退货"}
    return {"success": True, "message": f"收货地址已修改为：{new_address}"}
