# 智能客服 Agent · 设计说明文档

> 版本：v1.1 | 日期：2026-07-17 | 状态：Phase 1 完成，可运行

---

## 一、产品概述

### 1.1 产品定位
基于大语言模型（LLM）的多轮对话智能客服系统，支持上下文理解、情感识别和知识库检索，可无缝接入企业微信、钉钉等 IM 平台，实现 7×24 小时自动客服。

### 1.2 核心目标

| 指标 | 目标值 | 衡量方式 |
|------|--------|----------|
| 首响时间 | < 3 秒（含 RAG 检索） | P95 延迟监控 |
| 意图识别准确率 | ≥ 92% | 人工抽检 / 用户反馈 |
| 知识库问答命中率 | ≥ 85% | 检索召回率 + 答案采纳率 |
| 人工转接率 | ≤ 15% | 客服系统统计 |
| 并发支持 | 500 QPS | 压测验证 |

### 1.3 适用场景
- 售后咨询（退换货、物流、保修）
- 产品使用指导（FAQ、操作手册）
- 业务办理引导（开户、充值、预约）
- 内部 IT 服务台（密码重置、权限申请）

---

## 二、系统架构

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                        接入层 (Gateway)                       │
│   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────┐ │
│   │ 企业微信  │  │  钉钉    │  │  Web Chat │  │  API / SDK │ │
│   └────┬─────┘  └────┬─────┘  └────┬─────┘  └─────┬──────┘ │
│        └──────────────┴─────────────┴─────────────┘         │
│                            │                                 │
│                   ┌────────▼────────┐                       │
│                   │  Message Router  │                       │
│                   │  (消息统一路由)   │                       │
│                   └────────┬────────┘                       │
└────────────────────────────┼────────────────────────────────┘
                             │
┌────────────────────────────┼────────────────────────────────┐
│                      核心服务层                               │
│         ┌──────────────────▼──────────────────┐             │
│         │         Agent Orchestrator           │             │
│         │         (智能体编排引擎)              │             │
│         └──┬────────┬────────┬────────┬───────┘             │
│            │        │        │        │                      │
│    ┌───────▼──┐ ┌──▼────┐ ┌─▼────┐ ┌─▼────────┐           │
│    │ 意图识别  │ │ 对话  │ │ 知识  │ │ 情感分析  │           │
│    │ Intent   │ │ 管理  │ │ 检索  │ │ Sentiment │           │
│    │ Engine   │ │Memory │ │  RAG  │ │  Engine   │           │
│    └────┬─────┘ └──┬────┘ └──┬───┘ └─────┬─────┘           │
│         │          │         │            │                  │
│         └──────────┴────┬────┴────────────┘                 │
│                         │                                    │
│              ┌──────────▼──────────┐                        │
│              │    LLM Gateway       │                        │
│              │  (模型统一调用层)     │                        │
│              └──────────┬──────────┘                        │
└─────────────────────────┼───────────────────────────────────┘
                          │
┌─────────────────────────┼───────────────────────────────────┐
│                    基础设施层                                  │
│     ┌──────────┐  ┌────▼─────┐  ┌──────────┐  ┌──────────┐ │
│     │ 向量数据库 │  │ 关系数据库│  │ 缓存层    │  │ 消息队列  │ │
│     │ Milvus   │  │PostgreSQL│  │  Redis   │  │ RabbitMQ │ │
│     └──────────┘  └──────────┘  └──────────┘  └──────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 核心数据流

```
用户消息 → Gateway → 消息标准化 → Agent Orchestrator
                                        │
                    ┌───────────────────┼───────────────────┐
                    ▼                   ▼                   ▼
              意图识别引擎          情感分析引擎          上下文组装
              (分类/实体提取)      (正面/中性/负面)     (历史+知识检索)
                    │                   │                   │
                    └───────────────────┼───────────────────┘
                                        ▼
                                Prompt 拼装
                                        │
                                        ▼
                                  LLM 推理
                                        │
                              ┌─────────┴─────────┐
                              ▼                   ▼
                         置信度 ≥ 阈值       置信度 < 阈值
                              │                   │
                              ▼                   ▼
                         返回用户            转人工客服
```

---

## 三、技术选型

### 3.1 当前实现技术栈（Phase 1）

| 层次 | 技术 | 说明 |
|------|------|------|
| **LLM** | DeepSeek (deepseek-chat) | 兼容 OpenAI SDK，性价比高 |
| **Agent 框架** | LangChain + LangChain-OpenAI | ChatOpenAI 统一调用层 |
| **后端框架** | aiohttp (Python) | 异步高性能，轻量级 |
| **会话存储** | 内存存储 (MemoryStore) | Phase 1 使用 TTL 内存存储，后续迁移 Redis |
| **知识库** | 内置 FAQ | 8 条覆盖订单/退款/保修/账户场景 |

### 3.2 生产环境推荐技术栈（Phase 4 目标）

| 层次 | 技术 | 选型理由 |
|------|------|----------|
| **LLM** | GPT-4o / Claude Sonnet 4 | 推理能力强，支持 Function Calling，中文表现好 |
| **轻量模型** | GPT-4o-mini / Qwen3-8B | 意图识别、情感分析等子任务，降低延迟和成本 |
| **Agent 框架** | LangChain + LangGraph | 生态成熟，RAG 链、状态图编排、工具调用开箱即用 |
| **向量数据库** | Milvus / Qdrant | 高性能 ANN 检索，支持混合搜索（向量 + 关键词） |
| **关系数据库** | PostgreSQL 16 | 对话记录、用户画像、FAQ 管理 |
| **缓存** | Redis | 高频问答缓存、会话状态存储、限流计数 |
| **消息队列** | RabbitMQ / Kafka | 异步消息处理，平台回调解耦 |
| **后端框架** | FastAPI (Python) | 异步高性能，WebSocket 支持，自动 OpenAPI 文档 |
| **容器编排** | Docker + K8s | 弹性伸缩，灰度发布，服务治理 |
| **监控** | Prometheus + Grafana | 延迟、错误率、Token 消耗全链路监控 |
| **日志** | ELK Stack | 对话日志集中存储与检索 |

### 3.2 备选方案

| 场景 | 主方案 | 备选方案 |
|------|--------|----------|
| 私有化部署 | GPT-4o API | vLLM + Qwen3-72B 本地部署 |
| 向量库轻量化 | Milvus | Chroma / FAISS（适合小规模 PoC） |
| 消息通道 | 企业微信官方 API | WebSocket 长连接自建通道 |

---

## 四、核心模块设计

### 4.1 意图识别引擎

将用户自然语言映射到预定义的业务意图和槽位。

**意图 Schema 示例**：

| 意图 | 说明 | 槽位 | 示例问法 |
|------|------|------|----------|
| `order_query` | 查询订单状态 | order_id, phone | "我的订单到哪了" |
| `refund_request` | 申请退款/退货 | order_id, reason | "我要退货" |
| `product_consult` | 产品信息咨询 | product_name | "这个支持蓝牙吗" |
| `account_service` | 账户相关操作 | operation | "帮我重置密码" |
| `human_transfer` | 要求转人工 | - | "转人工" |
| `chitchat` | 闲聊/无关 | - | "你好" |

**三层识别策略**：

1. **规则快速匹配**：关键词语料库 + Regex，毫秒级命中高频意图
2. **轻量模型分类**：GPT-4o-mini + Few-shot Prompt，延迟 < 500ms
3. **深度推理兜底**：GPT-4o + Chain-of-Thought，处理多意图嵌套

### 4.2 对话管理与记忆

**多层记忆架构**：

| 记忆类型 | 存储介质 | 生命周期 | 示例 |
|----------|----------|----------|------|
| 短期记忆 | Redis (会话级) | 30 分钟无活动过期 | 本轮对话上下文 |
| 长期记忆 | PostgreSQL (用户级) | 永久 | 历史工单、偏好标签 |
| 摘要记忆 | 定期 LLM 压缩 | 跨会话持久化 | 用户问题画像摘要 |

**记忆压缩策略**：每积累 10 轮对话，调用 LLM 生成摘要存入长期记忆，短期缓冲区仅保留最近 5 轮。

### 4.3 知识库检索 (RAG)

**文档处理 Pipeline**：

```
原始文档 → 文档解析 → 智能分块 → Embedding → 向量入库
   │           │           │            │           │
   ▼           ▼           ▼            ▼           ▼
 PDF/Word   Unstructured 语义分割    text-embedding  Milvus
 网页/FAQ   /PyPDF2      512 token   -3-large       Index
```

**混合检索策略**：
1. 向量语义检索（Milvus ANN，召回 Top-K×2）
2. BM25 关键词检索（精确匹配补充）
3. RRF 融合去重（Reciprocal Rank Fusion）
4. Cross-encoder Rerank 精排（bge-reranker-v2）

**质量保障**：检索分数 < 0.6 自动降级为「为您转接人工」；每个答案附带源引用链接

### 4.4 情感分析与智能路由

| 情感标签 | 置信度要求 | 路由策略 |
|----------|-----------|----------|
| positive（正面） | - | 正常服务 |
| neutral（中性） | - | 正常服务 |
| negative（负面） | > 0.7 | 优先安抚 + 语气调整 |
| angry（愤怒） | > 0.8 | 立即转人工 + 工单标记 |
| urgent（紧急） | 关键词触发 | 立即转人工 |

同一会话内持续追踪情绪趋势，连续 3 轮负面则主动升级。

### 4.5 安全护栏 (Guardrails)

**输入过滤**：检测 Prompt 注入攻击、敏感词、越狱尝试

**输出过滤**：检测幻觉内容、品牌合规偏离、PII 信息泄露

**兜底策略**：
- 遇到无法处理的问题 → 主动建议转人工
- 涉及法律/医疗/金融建议 → 拒绝回答并引导至专业人员
- 检测到攻击性输入 → 礼貌结束对话

---

## 五、多平台接入

### 5.1 接入架构

采用 Adapter 模式，每个平台一个独立适配器，内部统一为 `UnifiedMessage` 格式：

```
┌─────────────────────────────────────────┐
│           Message Router                 │
│           (消息统一路由)                  │
└────┬──────────┬──────────┬──────────────┘
     │          │          │
┌────▼────┐ ┌───▼────┐ ┌──▼──────────┐
│ 企业微信  │ │  钉钉   │ │  Web Chat   │
│ Adapter  │ │ Adapter │ │  Adapter    │
├─────────┤ ├────────┤ ├─────────────┤
│ 消息解密  │ │ 消息验签 │ │ WebSocket   │
│ 回调验证  │ │ Outgoing│ │ REST API    │
│ 类型映射  │ │ 类型映射 │ │ 会话管理     │
└─────────┘ └────────┘ └─────────────┘
```

### 5.2 统一消息模型

```python
@dataclass
class UnifiedMessage:
    platform: str          # wecom / dingtalk / web
    user_id: str
    session_id: str
    content_type: str      # text / image / voice / file
    content: str
    raw_payload: dict      # 平台原始数据保留
    timestamp: datetime
```

### 5.3 企微接入关键步骤
1. 管理后台创建「企业内部应用」
2. 配置消息接收 URL + Token + AES Key
3. 实现 URL 验证（echostr 校验）
4. 消息加解密（AES + CorpID）
5. 配置应用权限并上线

---

## 六、数据库设计

### 6.1 核心表

**conversations（会话表）**

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | 会话唯一标识 |
| user_id | VARCHAR(128) | 用户 ID |
| platform | VARCHAR(32) | 平台来源 |
| intent | VARCHAR(64) | 最终识别意图 |
| sentiment | VARCHAR(16) | 情感标签 |
| status | VARCHAR(32) | active / closed / escalated |
| started_at | TIMESTAMPTZ | 开始时间 |
| ended_at | TIMESTAMPTZ | 结束时间 |

**messages（消息表）**

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGSERIAL PK | 消息 ID |
| conversation_id | UUID FK | 所属会话 |
| role | VARCHAR(16) | user / assistant / system |
| content | TEXT | 消息内容 |
| confidence | FLOAT | 置信度 |
| tokens_used | INT | Token 消耗 |
| latency_ms | INT | 响应延迟 |
| created_at | TIMESTAMPTZ | 创建时间 |

**knowledge_docs（知识库文档表）**

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | 文档 ID |
| title | VARCHAR(256) | 标题 |
| category | VARCHAR(64) | 分类 |
| content | TEXT | 原始内容 |
| chunk_count | INT | 分块数量 |
| version | INT | 版本号 |

**user_profiles（用户画像表）**

| 字段 | 类型 | 说明 |
|------|------|------|
| user_id | VARCHAR(128) PK | 用户 ID |
| platform | VARCHAR(32) | 平台来源 |
| name | VARCHAR(128) | 用户名 |
| tags | TEXT[] | 标签（VIP、投诉倾向等） |
| conversation_count | INT | 历史会话数 |
| avg_sentiment | FLOAT | 历史平均情感分 |

---

## 七、API 设计

### 7.1 接口列表（当前已实现）

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/` | 网页聊天界面 |
| `POST` | `/api/v1/chat/send` | 发送消息（意图识别+情感分析+知识检索+LLM生成） |
| `GET` | `/api/v1/chat/history/{session_id}` | 查询对话历史 |
| `GET` | `/api/v1/chat/health` | 健康检查 |
| `GET` | `/api/v1/chat/suggestions` | 推荐快捷问题 |
| `GET` | `/docs` | 跳转到聊天页面 |

### 7.2 后续计划接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `WS` | `/api/v1/chat/ws/{session_id}` | WebSocket 实时对话 |
| `POST` | `/api/v1/knowledge/upload` | 上传知识文档 |
| `GET` | `/api/v1/knowledge/search` | 知识库搜索 |
| `GET` | `/api/v1/stats/dashboard` | 运营数据看板 |

### 7.2 消息请求/响应示例

**Request**：
```json
POST /api/v1/chat/send
{
  "platform": "wecom",
  "user_id": "user_zhangsan",
  "session_id": "sess_abc123",
  "content": "我的订单到哪了？单号是20260715001",
  "content_type": "text"
}
```

**Response**：
```json
{
  "code": 0,
  "data": {
    "message_id": "msg_456",
    "content": "您好！您的订单 20260715001 当前状态为【运输中】，预计明天（7月18日）送达。需要我帮您查看更详细的位置吗？",
    "intent": "order_query",
    "confidence": 0.96,
    "sentiment": "neutral",
    "sources": [
      { "doc_title": "订单查询 FAQ", "chunk_id": "chunk_789", "relevance": 0.92 }
    ],
    "latency_ms": 1850,
    "suggestions": ["查看物流详情", "修改收货地址", "申请退款"]
  }
}
```

---

## 八、部署架构

### 8.1 生产拓扑

```
                    ┌──────────────┐
                    │  Nginx LB    │
                    │  (TLS 终结)   │
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
        ┌─────▼─────┐ ┌───▼───┐ ┌─────▼─────┐
        │ Gateway   │ │Gateway│ │ Gateway   │
        │ Pod × 2   │ │Pod    │ │ Pod × 2   │
        └─────┬─────┘ └───┬───┘ └─────┬─────┘
              │            │            │
        ┌─────▼────────────▼────────────▼─────┐
        │         Agent Service                │
        │    (HPA: 2-10 pods, CPU 70%)        │
        └────────────────┬────────────────────┘
                         │
        ┌────────────────┼────────────────────┐
        │                │                     │
   ┌────▼────┐    ┌──────▼──────┐    ┌───────▼──────┐
   │ Milvus  │    │ PostgreSQL  │    │    Redis     │
   │ Cluster │    │  Primary +  │    │   Sentinel   │
   │  3 节点  │    │  Read Replica│   │   3 节点      │
   └─────────┘    └─────────────┘    └──────────────┘
```

### 8.2 容量规划

| 规模 | 日消息量 | CPU | 内存 | GPU（如本地模型） |
|------|----------|-----|------|-------------------|
| 小型 | < 1 万 | 4C × 2 | 16 GB | 不需要（用 API） |
| 中型 | 1-10 万 | 8C × 3 | 32 GB | 1 × A10 |
| 大型 | 10 万+ | 16C × 5 | 64 GB | 2 × A100 |

---

## 九、开发路线图

```
Phase 1 · 基础搭建 (2 周)
├── 项目脚手架 (FastAPI + Docker)
├── LLM 接入层 (GPT-4o-mini)
├── 基础对话 API (/chat/send)
├── PostgreSQL 建表 + 会话存储
└── 简单 FAQ 知识库

Phase 2 · 核心能力 (3 周)
├── RAG 检索 Pipeline
├── 意图识别引擎
├── 多轮对话记忆管理
├── 情感分析模块
└── 安全护栏 (Guardrails)

Phase 3 · 平台接入 (2 周)
├── 企业微信 Adapter
├── 钉钉 Adapter
├── Web Chat 前端
└── 消息统一路由

Phase 4 · 生产就绪 (2 周)
├── K8s 部署 + HPA
├── Prometheus + Grafana 监控
├── ELK 日志收集
├── 压力测试与调优
└── 运营后台（知识管理 + 数据看板）

Phase 5 · 持续优化 (长期)
├── A/B 测试不同 Prompt 策略
├── 用户反馈闭环（赞/踩 → 自动优化）
├── 多语言支持
└── 语音消息接入
```

---

## 十、风险与应对

| 风险 | 概率 | 影响 | 应对措施 |
|------|------|------|----------|
| LLM 幻觉导致错误答复 | 中 | 高 | RAG 强绑定 + 置信度降级 + 高危场景人工审核 |
| API 延迟抖动 | 中 | 中 | 多模型 Fallback + 高频问答本地缓存 |
| 企业平台接口变更 | 低 | 高 | Adapter 解耦 + 接口变更监控 |
| 用户隐私泄露 | 低 | 极高 | PII 脱敏 + 输出过滤 + 加密存储 |
| 并发高峰服务降级 | 中 | 中 | 熔断限流 + 优雅降级为规则应答 |

---



---

## 十一、快速启动（Phase 1 已实现）

### 环境要求

- Python 3.10+
- DeepSeek API Key（或其他 OpenAI 兼容的 API）

### 启动步骤

```bash
# 1. 进入项目目录
cd customer-service-agent

# 2. 配置 API Key（首次使用）
# 编辑 .env 文件，修改 OPENAI_API_KEY 为你的 Key
# 默认使用 DeepSeek，如需切换 OpenAI 修改 OPENAI_BASE_URL

# 3. 安装依赖（如缺少）
pip install aiohttp langchain langchain-openai langchain-core pydantic pydantic-settings httpx python-dotenv tenacity

# 4. 启动
python -m app.main
```

### 访问

| 地址 | 说明 |
|------|------|
| `http://localhost:8000` | 网页聊天界面，可直接对话 |
| `http://localhost:8000/api/v1/chat/health` | 健康检查 |

### 测试请求

```bash
curl -X POST http://localhost:8000/api/v1/chat/send \
  -H "Content-Type: application/json" \
  -d '{"platform":"web","user_id":"test","content":"如何查询订单状态？","content_type":"text"}'
```

### 项目文件结构

```
customer-service-agent/
├── start.bat                  # Windows 一键启动脚本
├── .env                       # 环境配置（API Key 等）
├── app/
│   ├── main.py                # aiohttp 入口
│   ├── config.py              # 配置管理
│   ├── api/routes.py          # API 路由 + 对话编排流程
│   ├── core/
│   │   ├── llm.py             # LLM 网关（对话/意图/情感）
│   │   ├── memory.py          # 会话记忆（TTL 内存）
│   │   ├── guardrails.py      # 安全护栏（注入检测/PII脱敏）
│   │   └── knowledge.py       # 知识库检索（8条FAQ）
│   ├── models/schemas.py      # Pydantic 数据模型
│   └── db/database.py         # 内存存储引擎
├── static/index.html          # Web 聊天界面
└── knowledge/faq.md           # FAQ 知识源
```