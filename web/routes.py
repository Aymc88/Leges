"""
web/routes.py — Leges FastAPI Web App

Endpoints:
  GET  /api/config           当前配置
  GET  /api/presets          所有预设
  POST /api/config/preset    切换预设
  POST /api/search           搜索法案 (Spark: vector | Vercel: Deepseek)
  POST /api/generate         生成法案
  POST /api/legislators      推荐议员
  POST /api/petition/create  创建请愿
  POST /api/petition/sign    签名
  GET  /api/petition/{id}    查询请愿
  GET  /api/bills/{jurisdiction}/{bill_id}  法案详情
  GET  /api/health           健康检查
  GET  / → web/static/index.html
"""

from __future__ import annotations
import os, json, sys
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent))
from engine.config import get_active_config, PRESETS, ACTIVE_PRESET, JURISDICTIONS, LANGUAGES, all_jurisdictions

app = FastAPI(title="Leges", version="2.0.0")
_current_preset = "hackathon"
_embeddings, _metadata, _emb_dim = None, None, 384

# ── 轻量搜索 (numpy + Deepseek API) ──
def load_embeddings():
    global _embeddings, _metadata
    if _embeddings is None:
        try:
            import numpy as np
            data_dir = Path(__file__).parent.parent / "data"
            _embeddings = np.load(str(data_dir / "embeddings.npy"))
            with open(data_dir / "bill_metadata.json") as f:
                _metadata = json.load(f)
        except Exception:
            _embeddings, _metadata = [], []
    return _embeddings, _metadata

def embed_query_deepseek(query: str) -> list[float] | None:
    """用 Deepseek API 生成查询向量。"""
    import httpx
    api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
    if not api_key:
        return None
    try:
        resp = httpx.post(
            "https://api.deepseek.com/v1/embeddings",
            json={"model": "text-embedding-v3", "input": query},
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=30,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data and "data" in data and len(data["data"]) > 0:
                return data["data"][0]["embedding"]
    except Exception:
        pass
    return None

def search_local(query: str, top_k: int = 10) -> list[dict]:
    """向量搜索 (Spark: 本地模型 / Vercel: Deepseek API)。"""
    import numpy as np
    emb, meta = load_embeddings()
    if not len(emb):
        return []
    query_vec = None
    # Spark: 用本地 SentenceTransformer
    try:
        from sentence_transformers import SentenceTransformer
        m = SentenceTransformer("all-MiniLM-L6-v2")
        query_vec = m.encode([query])[0].tolist()
    except Exception:
        pass
    # Vercel: 用 Deepseek API (维度可能不同)
    if query_vec is None:
        query_vec = embed_query_deepseek(query)
        if query_vec and len(query_vec) != emb.shape[1]:
            query_vec = None  # 维度不匹配,无法向量搜索
    if query_vec is None:
        return []
    q = np.array(query_vec, dtype=np.float32)
    q_norm = np.linalg.norm(q)
    if q_norm > 0:
        q = q / q_norm
    e_norm = emb / np.linalg.norm(emb, axis=1).reshape(-1, 1)
    scores = np.dot(e_norm, q)
    idx = np.argsort(scores)[-top_k * 3:][::-1]
    results = []
    for i in idx:
        results.append({"id": meta[i]["bill_id"], "score": float(scores[i]), "document": meta[i]["title"], "metadata": meta[i]})
    return results[:top_k]

def search_deepseek(query: str, top_k: int = 10) -> list[dict]:
    """用 Deepseek Chat 搜索法案 (Vercel 无法向量搜索时的后备方案)。"""
    import httpx, json as j
    api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
    if not api_key:
        return []
    try:
        _, meta = load_embeddings()
        if not meta:
            return []
        # 关键词预过滤
        words = query.lower().split()
        candidates = []
        for m in meta:
            title = (m.get("title", "") or "").lower()
            if any(w in title for w in words):
                candidates.append(m)
        if not candidates:
            candidates = meta[:100]
        candidates = candidates[:40]
        bills_text = "\n".join([f"{m['bill_id']}|{m['jurisdiction']}|{m['title'][:100]}" for m in candidates])
        prompt = f"Query: \"{query}\"\n\nFind the most relevant bills from this list. Return ONLY bill IDs as a JSON array.\n\n{bills_text}"
        resp = httpx.post(
            "https://api.deepseek.com/chat/completions",
            json={"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}], "max_tokens": 300},
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=30,
        )
        text = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        import re
        bill_ids = re.findall(r'[A-Z]+-\d+|[A-Z]+\d+', text)
        meta_map = {m["bill_id"]: m for m in candidates}
        results = []
        for bid in bill_ids:
            if bid in meta_map:
                results.append({"id": bid, "score": 1.0, "document": meta_map[bid]["title"], "metadata": meta_map[bid]})
        return results[:top_k]
    except Exception:
        return []

# ── 静态文件 ──
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


class PresetSwitch(BaseModel):
    preset: str

class SearchRequest(BaseModel):
    query: str
    jurisdiction: str | None = None
    top_k: int = 10


# ── API: 配置 ──
@app.get("/api/config")
def api_config():
    cfg = get_active_config()
    return cfg.to_dict()

@app.get("/api/presets")
def api_presets():
    return {"presets": {k: {"key": v.key, "label_en": v.label_en, "label_zh": v.label_zh, "jurisdictions": v.jurisdictions, "default_language": v.default_language} for k, v in PRESETS.items()}, "active": ACTIVE_PRESET}

@app.post("/api/config/preset")
def api_set_preset(body: PresetSwitch):
    global _current_preset
    key = body.preset
    if key not in PRESETS:
        return JSONResponse({"error": f"未知预设: {key}"}, status_code=400)
    _current_preset = key
    import engine.config as cfg_mod
    cfg_mod.ACTIVE_PRESET = key
    return {"preset": key, "config": get_active_config().to_dict()}

# ── API: 健康检查 ──
@app.get("/api/health")
def api_health():
    return {"status": "ok", "mode": "spark+deepseek"}

# ── API: 搜索 ──
@app.post("/api/search")
def api_search(body: SearchRequest):
    try:
        # 优先用向量搜索(Spark),失败则用 Deepseek Chat(Vercel)
        results = search_local(body.query, body.top_k)
        if not results:
            results = search_deepseek(body.query, body.top_k)
        return {"results": results, "query": body.query}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
