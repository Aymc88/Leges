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
            data_dir = Path(__file__).parent.parent / "data"
            # 尝试 numpy (Spark 上有)
            import numpy as np
            _embeddings = np.load(str(data_dir / "embeddings.npy"))
        except Exception:
            try:
                # 无 numpy: 自己解析 .npy 文件
                with open(str(data_dir / "embeddings.npy"), "rb") as f:
                    f.seek(128)  # skip header
                    raw = f.read()
                    dim = 384
                    cnt = len(raw) // (dim * 4)
                    import struct
                    _embeddings = [list(struct.unpack(f"{dim}f", raw[i*dim*4:(i+1)*dim*4])) for i in range(cnt)]
            except Exception:
                _embeddings = []
        try:
            with open(data_dir / "bill_metadata.json") as f:
                _metadata = json.load(f)
        except Exception:
            _metadata = []
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

def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """纯 Python 余弦相似度"""
    dot = sum(a*b for a,b in zip(v1,v2))
    n1 = sum(a*a for a in v1)**0.5
    n2 = sum(b*b for b in v2)**0.5
    return dot/(n1*n2) if n1*n2 else 0

def search_local(query: str, top_k: int = 10) -> list[dict]:
    """向量搜索 (Spark: 本地模型 / Vercel: Deepseek API)。"""
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
        if query_vec and len(query_vec) != len(emb[0]) if len(emb) else 0:
            query_vec = None
    if query_vec is None:
        return []
    # 纯 Python 余弦相似度
    scored = [(cosine_similarity(query_vec, emb[i]), meta[i]) for i in range(len(emb))]
    scored.sort(key=lambda x: -x[0])
    results = [{"id": m["bill_id"], "score": s, "document": m["title"], "metadata": m} for s,m in scored[:top_k]]
    return results

def search_deepseek(query: str, top_k: int = 10) -> list[dict]:
    """纯关键词搜索法案 — 搜标题和ID，稳定快速。"""
    try:
        _, meta = load_embeddings()
        if not meta:
            return []
        words = query.lower().split()
        scored = []
        for m in meta:
            search_text = ((m.get("title", "") or "") + " " + (m.get("bill_id", "") or "")).lower()
            matches = sum(1 for w in words if w in search_text)
            if matches > 0:
                scored.append((matches, m))
        # 按匹配数排序
        scored.sort(key=lambda x: -x[0])
        results = [{"id": m["bill_id"], "score": s / len(words), "document": m["title"], "metadata": m}
                   for s, m in scored[:top_k]]
        return results
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
    emb, meta = load_embeddings()
    return {"status": "ok", "mode": "spark+deepseek", "embeddings": len(emb) if emb is not None and len(emb) else 0, "metadata": len(meta)}

# ── API: 搜索 ──
@app.post("/api/search")
def api_search(body: SearchRequest):
    try:
        # 按法域过滤(默认按预设)
        results = search_deepseek(body.query, body.top_k)
        if body.jurisdiction:
            results = [r for r in results if r.get("metadata",{}).get("jurisdiction") == body.jurisdiction]
        return {"results": results[:body.top_k], "query": body.query}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── API: 生成法案 ──
class GenerateRequest(BaseModel):
    topic: str; title: str = ""; style: str = "standard"; lang: str = "zh"; analysis: bool = False

@app.post("/api/generate")
def api_generate(body: GenerateRequest):
    try:
        import httpx, os
        api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
        base_url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic")
        model = os.environ.get("ANTHROPIC_MODEL", "deepseek-v4-flash")
        if not api_key:
            return JSONResponse({"error": "API not configured"}, status_code=500)

        if body.analysis:
            if body.style == "party":
                if body.lang == "zh":
                    prompt = f"分析政党投票率: {body.topic}\n\n加州: 民主党%? 共和党%?\n香港: 建制派%? 民主派%?\n澳门: 亲政府%? 民主派%?\n\n每行一个数字。"
                else:
                    prompt = f"Party vote analysis for: {body.topic}\n\nCA: Democrats XX% Republicans XX%\nHK: Pro-establishment XX% Democrats XX%\nMO: Pro-govt XX% Others XX%\n\nOne line per jurisdiction, replace XX with numbers."
            elif body.lang == "zh":
                prompt = f"你是一位立法分析师。请分析以下法案主题的通过可能性。\n\n主题: {body.topic}\n\n请给出:\n1. 估计通过率 (0-100%)\n2. 各政党投票倾向\n3. 支持因素 (2-3)\n4. 反对因素 (2-3)\n5. 最适合提出该法案的法域 (加州/香港/澳门) 及原因\n\n简明扼要。"
            else:
                prompt = f"You are a legislative analyst. Analyze passage likelihood for this bill topic.\n\nTopic: {body.topic}\n\nJurisdictions: CA=California(USA), HK=Hong Kong SAR(China), MO=Macau SAR(China). MO is Macau, NOT Missouri.\n\nProvide:\n1. Estimated pass rate (0-100%)\n2. Party breakdown per jurisdiction\n3. Supporting factors (2-3)\n4. Opposing factors (2-3)\n5. Best jurisdiction (CA/HK/MO only) and why\n\nConcise, 4-6 sentences."
        elif body.lang == "zh":
            guide = {"standard":"","detailed":"请写得非常详细，每一条款展开，800-1500字。","simple":"请写得简短精炼，200-400字。"}
            prompt = f"你是一位立法助理。请生成一份法案草案。\n\n标题: {body.title or body.topic}\n主题: {body.topic}\n{guide.get(body.style,'')}\n\n结构: 名称、目的、关键条款、实施机制、预期影响。输出中文。"
        else:
            guide = {"standard":"","detailed":"Be very detailed, 800-1500 words.","simple":"Be concise, 200-400 words."}
            prompt = f"You are a legislative drafter. Generate a bill draft.\n\nTitle: {body.title or body.topic}\nTopic: {body.topic}\n{guide.get(body.style,'')}\n\nStructure: title, purpose, key provisions, implementation, impact. Output English."

        with httpx.Client(timeout=90) as http:
            resp = http.post(f"{base_url}/messages", headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={"model": model, "max_tokens": 3000, "messages": [{"role": "user", "content": prompt}]})
            data = resp.json()
            text = "".join(b.get("text","") for b in data.get("content",[]) if b.get("type")=="text")
        return {"success": True, "generated": text or "No content", "title": body.title or body.topic[:50]}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── API: 找议员 ──
class LegislatorRequest(BaseModel):
    topic: str; jurisdiction: str = "CA"; lang: str = "en"

@app.post("/api/legislators")
def api_legislators(body: LegislatorRequest):
    try:
        import httpx, os, re, json
        api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
        base_url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic")
        model = os.environ.get("ANTHROPIC_MODEL", "deepseek-v4-flash")
        jur_names = {"CA":"California", "HK":"Hong Kong", "MO":"Macau"}
        if body.lang == "zh":
            prompt = f"推荐3-5位可能支持该法案的{jur_names.get(body.jurisdiction,'')}议员。\n\n主题: {body.topic}\n\n每人: 姓名、议院、选区、政党、支持理由。仅输出JSON数组，字段: name, chamber, district, party, reason。"
        else:
            prompt = f"Recommend 3-5 legislators in {jur_names.get(body.jurisdiction,'')} who would support this bill.\n\nTopic: {body.topic}\n\nEach: name, chamber, district, party, reason. Output ONLY JSON array with fields: name, chamber, district, party, reason."
        with httpx.Client(timeout=60) as http:
            resp = http.post(f"{base_url}/messages", headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={"model": model, "max_tokens": 1500, "messages": [{"role": "user", "content": prompt}]})
            text = "".join(b.get("text","") for b in resp.json().get("content",[]) if b.get("type")=="text")
        m = re.search(r'\[.*\]', text, re.DOTALL)
        legislators = json.loads(m.group()) if m else []
        return {"success": True, "legislators": legislators, "topic": body.topic}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── API: 请愿 ──
_petitions = {}; _petition_id_counter = 0

class PetitionCreateRequest(BaseModel):
    title: str; topic: str; goal: int = 2000

class PetitionSignRequest(BaseModel):
    petition_id: str; name: str = ""

@app.post("/api/petition/create")
def api_petition_create(body: PetitionCreateRequest):
    global _petition_id_counter; _petition_id_counter += 1
    pid = f"pet-{_petition_id_counter}"
    _petitions[pid] = {"id": pid, "title": body.title, "topic": body.topic, "goal": body.goal, "signatures": []}
    return {"success": True, "petition": _petitions[pid]}

@app.get("/api/petition/{petition_id}")
def api_petition_get(petition_id: str):
    p = _petitions.get(petition_id)
    if not p:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return {"id": p["id"], "title": p["title"], "topic": p["topic"], "goal": p["goal"], "count": len(p["signatures"]), "signatures": p["signatures"][-20:]}

@app.post("/api/petition/sign")
def api_petition_sign(body: PetitionSignRequest):
    p = _petitions.get(body.petition_id)
    if not p:
        return JSONResponse({"error": "Not found"}, status_code=404)
    p["signatures"].append({"name": body.name or "Anonymous"})
    return {"success": True, "count": len(p["signatures"]), "goal": p["goal"]}


# ── API: 法案详情 ──
@app.get("/api/bills/{jurisdiction}/{bill_id}")
def api_bill_detail(jurisdiction: str, bill_id: str):
    jur_file = {"CA": "ca_bills.jsonl", "MO": "mo_laws.jsonl", "HK": "hk_bills.jsonl"}
    fname = jur_file.get(jurisdiction)
    if not fname:
        return JSONResponse({"error": "Unknown jurisdiction"}, status_code=404)
    path = Path(__file__).parent.parent / "output" / fname
    if not path.exists():
        return JSONResponse({"error": "Data not found"}, status_code=404)
    with open(path) as f:
        for line in f:
            rec = json.loads(line)
            rid = rec.get("bill_id") or f"MO-{rec.get('law_id', '')}"
            if rid == bill_id:
                return rec
    return JSONResponse({"error": "Not found"}, status_code=404)


# ── SPA 入口 ──
@app.get("/")
def index():
    html_path = static_dir / "index.html"
    if html_path.exists():
        return HTMLResponse(html_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Leges</h1><p>Frontend not found.</p>")
