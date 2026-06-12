# voidchat

可插拔角色 AI 聊天框架。丢一个 `soul.md` 就能聊天。

## 快速开始

```bash
git clone https://github.com/Yunlk/voidchat.git
cd voidchat
cp .env.example .env
```

编辑 `.env`，填入你的 API 密钥：

```env
SILICONFLOW_KEY=sk-your-key-here
API_BASE=https://api.siliconflow.cn/v1/chat/completions
DEFAULT_MODEL=deepseek-ai/DeepSeek-V3
```

```bash
cd web
docker compose up -d --build
```

打开 `http://localhost:8000`，选择角色开始聊天。

### 不用 Docker？

```bash
cd web
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

## 角色系统

角色是 `characters/` 目录下的子文件夹。每个角色两个文件：

```
characters/
└── my-oc/
    ├── manifest.json   # 元数据
    └── soul.md         # 系统提示词（完整人设）
```

### manifest.json

```json
{
  "id": "my-oc",
  "name": "角色显示名",
  "greeting": "打开聊天时的第一句话",
  "description": "卡片上的简短描述",
  "model": "deepseek-ai/DeepSeek-V3"
}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `id` | 是 | 唯一标识，URL 里用 |
| `name` | 是 | 显示名 |
| `greeting` | 是 | 初始消息 |
| `description` | 否 | 选择页卡片描述 |
| `model` | 否 | 覆盖默认模型 |

### soul.md

角色的完整 system prompt。后端会作为第一条 system 消息注入。写法和语气完全自由。

### 运行时管理

| 操作 | 方式 |
|------|------|
| 添加角色 | 在 `characters/` 下新建目录 + 两个文件 |
| 删除角色 | 删掉对应目录 |
| 修改角色 | 直接编辑 soul.md 或 manifest.json |
| 热重载 | `POST /api/characters/reload`（不需要重启容器） |
| 查看列表 | `GET /api/characters` |

Docker 部署时 `characters/` 通过 volume 挂载，宿主机直接编辑即可。

## 自定义 API

兼容任何 OpenAI-compatible API。通过环境变量控制：

| 环境变量 | 说明 | 默认值 |
|----------|------|--------|
| `SILICONFLOW_KEY` | API 密钥（也支持 `OPENAI_API_KEY`） | — |
| `API_BASE` | Chat Completions 端点完整 URL | `https://api.siliconflow.cn/v1/chat/completions` |
| `DEFAULT_MODEL` | 默认模型 | `deepseek-ai/DeepSeek-V3` |
| `CHARACTERS_DIR` | 角色目录路径 | `../characters` |

### 示例

**用 DeepSeek 官方 API：**
```env
SILICONFLOW_KEY=sk-xxxxxxxx
API_BASE=https://api.deepseek.com/v1/chat/completions
DEFAULT_MODEL=deepseek-chat
```

**用 Ollama 本地模型：**
```env
SILICONFLOW_KEY=ollama
API_BASE=http://localhost:11434/v1/chat/completions
DEFAULT_MODEL=qwen2.5:14b
```

**用 OpenAI：**
```env
OPENAI_API_KEY=sk-xxxxxxxx
API_BASE=https://api.openai.com/v1/chat/completions
DEFAULT_MODEL=gpt-4o-mini
```

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/` | 角色选择页 |
| `GET` | `/chat?c=<id>` | 聊天页 |
| `GET` | `/api/characters` | 角色列表 JSON |
| `POST` | `/api/chat` | 发送消息（SSE 流式返回） |
| `POST` | `/api/reset` | 重置会话 |
| `GET` | `/api/session?sid=xxx` | 查看会话状态 |
| `POST` | `/api/characters/reload` | 热重载角色 |
| `GET` | `/api/dl/:id` | 下载端点（角色恶作剧用） |
| `POST` | `/api/dl-abort` | 中断下载 |

### POST /api/chat

```json
{
  "character": "my-oc",
  "message": "你好",
  "session_id": "可选的会话ID"
}
```

返回 SSE 流，每 token 一个事件，最后 `[DONE]`。

## 消息特性

### [MSG] 拆分

角色回复中可以用 `[MSG]` 将长回复拆成多条气泡。前端逐条播放，间隔 400ms。

```
第一句话。
[MSG]
第二句话。
[MSG]
最后一句。
```

### DL_SEQ 恶作剧序列

角色可以用下载恶作剧：

```
[DL_SEQ]
……想要？给你。
[DL:START]soul.md
真以为我会给你吗？
[DL:CANCEL]
……没有这个文件。
[/DL_SEQ]
```

`[DL:START]文件名` 触发浏览器真实下载（iframe），前端 `[DL:CANCEL]` 延时 800ms 后移除 iframe 并通知后端中断流。

## Docker 架构

```
                  ┌──────────────────┐
Browser :8000 ───►│  nginx (alpine)  │
                  │  :80             │
                  ├──────────────────┤
                  │ /static/*        │──► 静态文件直出 (.css/.js)
                  │ /api/*           │──► 代理 → voidchat:8000
                  │ /chat            │──► 代理 → voidchat:8000
                  │ /                │──► 代理 → voidchat:8000
                  └──────────────────┘
                            │
                  ┌────────▼────────┐
                  │  voidchat (自建) │
                  │  FastAPI :8000   │
                  │                  │
                  │ characters/ ─────│──► volume 挂载 ../characters
                  │ .env ────────────│──► env_file
                  └──────────────────┘
```

### docker-compose.yml

```yaml
services:
  voidchat:
    build: .                        # 当前目录 Dockerfile
    env_file: .env                  # 密钥 / API 地址
    volumes:
      - ../characters:/characters   # 角色文件实时同步
    restart: unless-stopped

  nginx:
    image: nginx:alpine
    ports:
      - "8000:80"                   # 对外暴露
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - ./static:/usr/share/nginx/html/static:ro
    depends_on:
      - voidchat
    restart: unless-stopped
```

### nginx 做了什么

| 功能 | 说明 |
|------|------|
| 静态直出 | CSS/JS 由 nginx 直出，7 天缓存，不经过 Python |
| API 代理 | `/api/*` → FastAPI，`Proxy-*` 头全部转发 |
| SSE 支持 | `proxy_buffering off`，读超时 300s |
| 限流 | `/api/chat` 每 IP 每分钟最多 10 次，突发 5 |
| 安全头 | `X-Content-Type-Options`, `X-Frame-Options` 等 |
| GZip | 文本/JSON/CSS/JS 自动压缩 |

### 目录结构（web/）

```
web/
├── Dockerfile              # voidchat 后端镜像
├── docker-compose.yml      # 编排 nginx + voidchat
├── nginx.conf              # nginx 配置
├── main.py                 # FastAPI 应用
├── requirements.txt        # Python 依赖
└── static/                 # 前端静态文件
    ├── index.html          # 角色选择页
    ├── chat.html           # 聊天页
    ├── css/style.css
    └── js/app.js
```

## 前端

纯静态 HTML/CSS/JS，零框架，零构建步骤。

- **角色选择页**：暗色卡片网格，hover 高亮
- **聊天页**：消息气泡、角色名前缀、CSS 渐入动画
- 自适应 640px 断点，移动端可用
- SSE 流式渲染，`[MSG]` 拆分播放

## 技术栈

- Python 3.11+ / FastAPI / httpx（流式代理）
- uvicorn
- Docker + docker compose
- 纯 HTML/CSS/JS 前端

## 许可

MIT
