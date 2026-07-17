# 🤖 智能客服 Agent

基于大语言模型的多轮对话智能客服系统（Phase 1 脚手架）。

## 技术栈

- **框架**: aiohttp
- **AI**: LangChain + DeepSeek API（兼容 OpenAI SDK）
- **存储**: 内存会话管理
- **知识库**: 内置 FAQ

## 快速启动

### 1. 配置环境变量

编辑 `.env`，填入你的 DeepSeek API Key：

```env
OPENAI_API_KEY=sk-your-deepseek-key-here
OPENAI_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
```

### 2. 启动服务（本地 Python 包已预装，无需 pip install）

```bash
python -m app.main
```

### 3. 测试

```bash
curl -X POST http://localhost:8000/api/v1/chat/send -H "Content-Type: application/json" -d "{\"platform\":\"web\",\"user_id\":\"test\",\"content\":\"如何查询订单？\",\"content_type\":\"text\"}"
```

## 项目结构

```
app/
├── main.py           # aiohttp 入口
├── config.py         # 配置管理
├── api/routes.py     # API 路由 + 对话流程编排
├── core/
│   ├── llm.py        # LLM 网关（对话、意图、情感）
│   ├── memory.py     # 对话记忆（内存存储）
│   ├── guardrails.py  # 安全护栏
│   └── knowledge.py  # 知识库检索
├── models/schemas.py # Pydantic 数据模型
└── db/database.py    # 内存存储
```
