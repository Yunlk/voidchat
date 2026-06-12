# voidchat — 可插拔角色 AI 聊天框架
#
# 角色文件放在 ../characters/<id>/
#   manifest.json → 元数据（name, greeting, model, description）
#   soul.md       → system prompt
#
# 环境变量：
#   SILICONFLOW_KEY   — API 密钥（兼容 OPENAI_API_KEY）
#   API_BASE          — 自定义 API 地址（默认 矽基流动）
#   DEFAULT_MODEL     — 默认模型（默认 deepseek-ai/DeepSeek-V3）
#   CHARACTERS_DIR    — 角色目录路径（默认 ../characters）

import os, re, json, uuid, asyncio, logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import StreamingResponse, JSONResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import httpx

# ── config ──────────────────────────────────────────────

CHARACTERS_DIR = Path(os.getenv("CHARACTERS_DIR", "../characters")).resolve()
API_KEY = os.getenv("SILICONFLOW_KEY", os.getenv("OPENAI_API_KEY", ""))
API_BASE = os.getenv("API_BASE", "https://api.siliconflow.cn/v1/chat/completions")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "deepseek-ai/DeepSeek-V3")
STATIC_DIR = Path(__file__).parent / "static"
CORS_ORIGINS = ["*"]

log = logging.getLogger("uvicorn.error")

# ── character loader ────────────────────────────────────

def load_characters() -> dict[str, dict]:
    chars = {}
    if not CHARACTERS_DIR.exists():
        return chars
    for d in sorted(CHARACTERS_DIR.iterdir()):
        if not d.is_dir():
            continue
        mf = d / "manifest.json"
        sf = d / "soul.md"
        if not mf.exists():
            continue
        try:
            manifest = json.loads(mf.read_text(encoding="utf-8"))
        except Exception:
            continue
        cid = manifest.get("id", d.name)
        chars[cid] = {
            "id": cid,
            "name": manifest.get("name", cid),
            "greeting": manifest.get("greeting", "……"),
            "description": manifest.get("description", ""),
            "model": manifest.get("model", DEFAULT_MODEL),
            "soul": sf.read_text(encoding="utf-8") if sf.exists() else "",
        }
    return chars

characters = load_characters()

def reload_characters():
    global characters
    characters = load_characters()
    log.info(f"characters reloaded: {list(characters.keys())}")

# ── app ─────────────────────────────────────────────────

app = FastAPI(title="voidchat")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ── session store ───────────────────────────────────────
# { session_id: { "character": cid, "history": [...] } }

sessions: dict[str, dict] = {}
active_downloads: dict[str, asyncio.Event] = {}

def get_or_create_session(sid: str, cid: str) -> dict:
    if sid not in sessions:
        sessions[sid] = {"character": cid, "history": []}
    return sessions[sid]

# ── endpoints ───────────────────────────────────────────

@app.get("/api/characters")
async def list_characters():
    return [
        {
            "id": c["id"],
            "name": c["name"],
            "description": c["description"],
            "greeting": c["greeting"],
        }
        for c in characters.values()
    ]

@app.post("/api/chat")
async def chat(req: Request):
    body = await req.json()
    cid = body.get("character", "")
    msg = body.get("message", "").strip()
    sid = body.get("session_id", str(uuid.uuid4()))

    if cid not in characters:
        raise HTTPException(404, f"character '{cid}' not found")

    char = characters[cid]
    session = get_or_create_session(sid, cid)

    if not msg:
        raise HTTPException(400, "empty message")

    session["history"].append({"role": "user", "content": msg})

    # build messages
    messages = [{"role": "system", "content": char["soul"]}]
    messages += session["history"][-32:]  # keep last 32 turns

    model = char.get("model", DEFAULT_MODEL)
    log.info(f"chat → {cid} ({model}) [{len(messages)} msgs]")

    async def stream():
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST", API_BASE,
                headers={
                    "Authorization": f"Bearer {API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "stream": True,
                    "temperature": 0.85,
                    "max_tokens": 2048,
                },
            ) as resp:
                full = ""
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk["choices"][0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            full += content
                            yield f"data: {json.dumps({'token': content})}\n\n"
                    except Exception:
                        continue
        session["history"].append({"role": "assistant", "content": full})
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.post("/api/reset")
async def reset_session(req: Request):
    body = await req.json()
    sid = body.get("session_id", "")
    cid = body.get("character", "")
    if sid in sessions:
        sessions[sid]["history"] = []
        sessions[sid]["character"] = cid
    return {"ok": True}


@app.get("/api/session")
async def get_session(sid: str = Query("")):
    if sid in sessions:
        return {"character": sessions[sid]["character"], "history_len": len(sessions[sid]["history"])}
    return {"character": "", "history_len": 0}


# ── download (恶作剧用) ─────────────────────────────────

@app.get("/api/dl/{dl_id}")
async def download(dl_id: str):
    cancel = asyncio.Event()
    active_downloads[dl_id] = cancel

    async def stream():
        chunk = b"\x00" * (256 * 1024)
        try:
            for _ in range(2000):
                if cancel.is_set():
                    break
                yield chunk
                await asyncio.sleep(0.08)
        finally:
            active_downloads.pop(dl_id, None)

    return StreamingResponse(
        stream(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="data_{dl_id}.bin"'},
    )


@app.post("/api/dl-abort")
async def abort_download(req: Request):
    body = await req.json()
    dl_id = body.get("id", "")
    if dl_id in active_downloads:
        active_downloads[dl_id].set()
        return {"ok": True}
    return {"ok": False, "error": "not found"}


# ── character admin ─────────────────────────────────────

@app.post("/api/characters/reload")
async def api_reload():
    reload_characters()
    return {"ok": True, "characters": list(characters.keys())}


# ── frontend ────────────────────────────────────────────

@app.get("/chat")
async def chat_page():
    return FileResponse(str(STATIC_DIR / "chat.html"))


@app.get("/", response_class=HTMLResponse)
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))
