# AI Assistant 架构设计

## 系统概览

```
┌─────────────────────────────────────────────────────────────┐
│                        Mac mini                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                   AI Assistant                       │    │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────────┐   │    │
│  │  │  Web UI   │──│ API Server│──│ OpenAI Client │   │    │
│  │  │  (前端)   │  │  (FastAPI)│  │ (OpenAI SDK)  │   │    │
│  │  └───────────┘  └─────┬─────┘  └───────────────┘   │    │
│  │                       │                             │    │
│  │            ┌──────────┴──────────┐                 │    │
│  │            │                     │                 │    │
│  │      ┌─────▼─────┐        ┌──────▼──────┐         │    │
│  │      │  Memory   │        │ File Store  │         │    │
│  │      │ (SQLite)  │        │ (本地文件)   │         │    │
│  │      └───────────┘        └─────────────┘         │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌───────────────────┐
                    │    OpenAI API     │
                    │ (api.openai.com)  │
                    └───────────────────┘
```

## 技术栈

| 组件 | 技术选择 | 理由 |
|------|---------|------|
| 后端 | Python + FastAPI | 简单、异步、与 OpenAI SDK 集成好 |
| 前端 | HTML + CSS + Vanilla JS | v1 先最简单，后续可换 React |
| 数据库 | SQLite | 本地运行、零配置、够用 |
| LLM 集成 | OpenAI Python SDK (gpt-4o) | 最新模型 |
| 文件存储 | 本地文件系统 | 简单直接 |

## 目录结构

```
assistant/
├── ARCHITECTURE.md          # 本文件
├── server/
│   ├── main.py              # FastAPI 入口
│   ├── routes/
│   │   ├── chat.py          # 对话 API
│   │   ├── files.py         # 文件上传 API
│   │   └── status.py        # 状态 API
│   ├── services/
│   │   ├── openai_client.py # OpenAI API 封装
│   │   └── memory.py        # Memory 管理
│   └── models/
│       └── schemas.py       # Pydantic 模型
├── memory/
│   ├── conversations.db     # SQLite 数据库
│   └── files/               # 上传的文件
├── ui/
│   ├── index.html           # 主页面
│   ├── style.css            # 样式
│   └── app.js               # 前端逻辑
├── config.py                # 配置
└── requirements.txt         # Python 依赖
```

## 核心组件

### 1. API Server (FastAPI)

```python
# 主要端点
POST /api/chat          # 发送消息，获取回复
GET  /api/conversations # 获取对话列表
GET  /api/conversation/{id} # 获取单个对话
POST /api/upload        # 上传文件（图片/PDF）
GET  /api/status        # 系统状态
```

### 2. Memory 系统

**存储内容**：
- 对话历史（conversation_id, messages, created_at）
- 文件元数据（file_id, path, type, summary）
- 用户偏好（key-value）

**SQLite Schema**：
```sql
CREATE TABLE conversations (
    id TEXT PRIMARY KEY,
    title TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE TABLE messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT,
    role TEXT,  -- 'user' | 'assistant'
    content TEXT,
    files TEXT, -- JSON array of file_ids
    created_at TIMESTAMP
);

CREATE TABLE files (
    id TEXT PRIMARY KEY,
    path TEXT,
    type TEXT,  -- 'image' | 'pdf'
    summary TEXT,
    created_at TIMESTAMP
);
```

### 3. OpenAI Client

```python
# 核心功能
- send_message(conversation_history, new_message, files) -> response
- 自动处理 multimodal（图片作为 base64，使用 gpt-4o vision）
- 自动记录 API 调用日志
```

### 4. Web UI

**功能**：
- 输入框 + 发送按钮
- 消息历史显示（支持 Markdown 渲染）
- 文件上传按钮（图片/PDF）
- 状态面板：
  - AI Assistant 版本号
  - 运行时间（uptime）
  - 消息计数

## 数据流

```
1. 用户输入消息 + 可选文件
          │
          ▼
2. Web UI 发送 POST /api/chat
          │
          ▼
3. API Server 接收请求
          │
          ├─ 保存用户消息到 Memory
          │
          ├─ 如果有文件，处理并保存
          │
          ▼
4. OpenAI Client 调用 OpenAI API (gpt-4o)
          │
          ▼
5. 收到响应
          │
          ├─ 保存 assistant 消息到 Memory
          │
          ▼
6. 返回响应给 Web UI
          │
          ▼
7. Web UI 显示响应
```

## 配置

```python
# config.py
# API key 存放在 .claude/secrets.env（已 gitignore）
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL = "gpt-4o"
DATABASE_PATH = "memory/conversations.db"
FILES_PATH = "memory/files"
HOST = "127.0.0.1"
PORT = 8080
```

## 启动方式

```bash
cd /Users/zelin/Startups/Genesis/assistant
pip install -r requirements.txt
python -m server.main
# 访问 http://127.0.0.1:8080
```

## 与 Claude Code 的关系

- Claude Code 读取此文档了解产品架构
- Claude Code 迭代实现 `assistant/` 下的代码
- AI Assistant 运行时独立，不依赖 Claude Code
- Web UI 显示 AI Assistant 自身状态（版本、运行时间、消息数）
- **注意**: AI Assistant 不显示 Claude Code 的开发状态（它们是独立的系统）

## v1 优先级

1. 基础对话功能（无文件）
2. 对话持久化
3. 简单 Web UI
4. 文件上传（图片）
5. PDF 支持
6. 状态面板
