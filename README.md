# voidchat

可插拔角色 AI 聊天框架。丢一个 `soul.md` 就能聊天。

## 快速开始

```bash
cp .env.example .env
# 编辑 .env，填入你的 API Key
cd web
docker compose up -d --build
```

打开 `http://localhost:8000`

## 角色

角色文件放在 `characters/` 目录下，每个角色一个子目录：

```
characters/
└── my-oc/
    ├── manifest.json   # 元数据
    └── soul.md         # 系统提示词
```

**manifest.json**：
```json
{
  "id": "my-oc",
  "name": "角色名",
  "greeting": "第一句话",
  "description": "简短描述",
  "model": "deepseek-ai/DeepSeek-V3"
}
```

热重载：`POST /api/characters/reload`

## 自定义

| 环境变量 | 说明 | 默认值 |
|----------|------|--------|
| `SILICONFLOW_KEY` | API 密钥 | — |
| `API_BASE` | 自定义 API 地址 | 矽基流动 |
| `DEFAULT_MODEL` | 默认模型 | `deepseek-ai/DeepSeek-V3` |
| `CHARACTERS_DIR` | 角色目录 | `../characters` |

兼容任何 OpenAI-compatible API。

## 内置角色

- **啟空** — 17岁，高二。Ψ-7样本。前协议执行者。
- **ネム** — 19岁。元キャバ嬢。地雷女。あなたのことがだいすき。

## 技术栈

FastAPI + 零 JS 框架前端 + Docker。纯静态 HTML/CSS/JS，无构建步骤。
