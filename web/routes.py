"""
web/routes.py — Leges FastAPI Web App
"""
from __future__ import annotations
import os, json, sys, re, struct
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent))
from engine.config import get_active_config, PRESETS, ACTIVE_PRESET

app = FastAPI(title="Leges", version="2.0.0")
_current_preset = "hackathon"
_embeddings, _metadata, _emb_dim = None, None, 384

def load_embeddings():
    global _embeddings, _metadata
    if _embeddings is None:
        try:
            data_dir = Path(__file__).parent.parent / "data"
            import numpy as np
            _embeddings = np.load(str(data_dir / "embeddings.npy"))
        except Exception:
            try:
                with open(str(Path(__file__).parent.parent / "data" / "embeddings.npy"), "rb") as f:
                    f.seek(128)
                    raw = f.read()
                    dim, cnt = 384, len(raw) // (384 * 4)
                    _embeddings = [list(struct.unpack(f"{dim}f", raw[i*dim*4:(i+1)*dim*4])) for i in range(cnt)]
            except Exception:
                _embeddings = []
        try:
            with open(Path(__file__).parent.parent / "data" / "bill_metadata.json") as f:
                _metadata = json.load(f)
        except Exception:
            _metadata = []
    return _embeddings, _metadata

def cosine_similarity(v1, v2):
    dot = sum(a*b for a,b in zip(v1,v2))
    n1 = sum(a*a for a in v1)**0.5
    n2 = sum(b*b for b in v2)**0.5
    return dot/(n1*n2) if n1*n2 else 0

def search_keyword(query: str, top_k: int = 10) -> list[dict]:
    try:
        _, meta = load_embeddings()
        if not meta: return []
        words = query.lower().split()
        scored = []
        for m in meta:
            txt = ((m.get("title","") or "") + " " + (m.get("bill_id","") or "")).lower()
            matches = sum(1 for w in words if w in txt)
            if matches > 0:
                scored.append((matches, m))
        scored.sort(key=lambda x: -x[0])
        return [{"id": m["bill_id"], "score": s/len(words), "document": m["title"], "metadata": m} for s,m in scored[:top_k]]
    except Exception:
        return []

static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

class PresetSwitch(BaseModel):
    preset: str
class SearchRequest(BaseModel):
    query: str; jurisdiction: str | None = None; top_k: int = 10

@app.get("/api/config")
def api_config():
    return get_active_config().to_dict()

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

@app.get("/api/health")
def api_health():
    emb, meta = load_embeddings()
    return {"status": "ok", "mode": "spark+deepseek", "embeddings": len(emb) if (emb is not None and len(emb)) else 0, "metadata": len(meta)}

@app.post("/api/search")
def api_search(body: SearchRequest):
    try:
        query = body.query
        # 如果查询含非ASCII(中文),先翻译成英文
        if not query.isascii():
            try:
                import httpx, os
                api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
                base_url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic")
                model = os.environ.get("ANTHROPIC_MODEL", "deepseek-v4-flash")
                if api_key:
                    resp = httpx.post(f"{base_url}/messages", headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                        json={"model": model, "max_tokens": 100, "messages": [{"role": "user", "content": f"Translate this Chinese query to English keywords for bill search. ONLY output the English keywords, nothing else: {query}"}]}, timeout=30)
                    text = "".join(b.get("text","") for b in resp.json().get("content",[]) if b.get("type")=="text").strip()
                    if text: query = text.split('\n')[0].strip('"\'')
            except Exception:
                pass
        # 按预设过滤
        jur_set = {body.jurisdiction} if body.jurisdiction else set(j.code for j in get_active_config().jurisdictions or [])
        results = search_keyword(query, body.top_k * 2)
        results = [r for r in results if r.get("metadata",{}).get("jurisdiction") in jur_set] if jur_set else results
        return {"results": results[:body.top_k], "query": body.query}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

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
                    prompt = f"分析政党投票率: {body.topic}\n\n加州: 民主党 XX% 共和党 XX%\n香港: 建制派 XX% 民主派 XX%\n澳门: 亲政府 XX% 其他 XX%\n\n每行一个。"
                else:
                    prompt = f"Party vote analysis for: {body.topic}\n\nCA: Democrats XX% Republicans XX%\nHK: Pro-establishment XX% Democrats XX%\nMO: Pro-govt XX% Others XX%\n\nOne per line."
            elif body.lang == "zh":
                prompt = f"你是一位立法分析师。请分析以下法案主题的通过可能性。\n\n主题: {body.topic}\n\n请给出:\n1. 估计通过率 (0-100%)\n2. 各政党投票倾向\n3. 支持因素 (2-3)\n4. 反对因素 (2-3)\n5. 最适合提出该法案的法域 (加州/香港/澳门) 及原因\n\n简明扼要。"
            else:
                prompt = f"You are a legislative analyst. Analyze passage likelihood for this bill topic.\n\nTopic: {body.topic}\n\nJurisdictions: CA=California(USA), HK=Hong Kong SAR(China), MO=Macau SAR(China). MO is Macau, NOT Missouri.\n\nProvide:\n1. Estimated pass rate (0-100%)\n2. Party breakdown per jurisdiction\n3. Supporting factors (2-3)\n4. Opposing factors (2-3)\n5. Best jurisdiction (CA/HK/MO only) and why\n\nConcise, 4-6 sentences."
        elif body.lang == "zh":
            guide = {"standard":"","detailed":"请写详细，800-1500字。","simple":"请写简短，200-400字。"}
            prompt = f"你是一位立法助理。请生成一份法案草案。\n\n标题: {body.title or body.topic}\n主题: {body.topic}\n{guide.get(body.style,'')}\n\n结构: 名称、目的、关键条款、实施机制、预期影响。输出中文。"
        else:
            guide = {"standard":"","detailed":"Be very detailed, 800-1500 words.","simple":"Be concise, 200-400 words."}
            prompt = f"You are a legislative drafter. Generate a bill draft.\n\nTitle: {body.title or body.topic}\nTopic: {body.topic}\n{guide.get(body.style,'')}\n\nStructure: title, purpose, key provisions, implementation, impact. Output English."
        with httpx.Client(timeout=90) as http:
            resp = http.post(f"{base_url}/messages", headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={"model": model, "max_tokens": 3000, "messages": [{"role": "user", "content": prompt}]})
            text = "".join(b.get("text","") for b in resp.json().get("content",[]) if b.get("type")=="text")
        return {"success": True, "generated": text or "No content", "title": body.title or body.topic[:50]}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

class LegislatorRequest(BaseModel):
    topic: str; jurisdiction: str = "CA"; lang: str = "en"

@app.post("/api/legislators")
def api_legislators(body: LegislatorRequest):
    try:
        import httpx, json, re, os
        api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
        base_url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic")
        model = os.environ.get("ANTHROPIC_MODEL", "deepseek-v4-flash")
        jn = {"CA":"California","HK":"Hong Kong","MO":"Macau"}
        if body.lang == "zh":
            prompt = f"推荐3-5位支持该法案的{jn.get(body.jurisdiction,'')}议员。主题: {body.topic}\n\n输出JSON: name, chamber, district, party, reason"
        else:
            prompt = f"Recommend 3-5 legislators in {jn.get(body.jurisdiction,'')} for this topic: {body.topic}\n\nOutput JSON: name, chamber, district, party, reason"
        with httpx.Client(timeout=60) as http:
            resp = http.post(f"{base_url}/messages", headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={"model": model, "max_tokens": 1500, "messages": [{"role": "user", "content": prompt}]})
            text = "".join(b.get("text","") for b in resp.json().get("content",[]) if b.get("type")=="text")
        m = re.search(r'\[.*\]', text, re.DOTALL)
        return {"success": True, "legislators": json.loads(m.group()) if m else [], "topic": body.topic}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

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
    if not p: return JSONResponse({"error": "Not found"}, status_code=404)
    return {"id": p["id"], "title": p["title"], "topic": p["topic"], "goal": p["goal"], "count": len(p["signatures"]), "signatures": p["signatures"][-20:]}
@app.post("/api/petition/sign")
def api_petition_sign(body: PetitionSignRequest):
    p = _petitions.get(body.petition_id)
    if not p: return JSONResponse({"error": "Not found"}, status_code=404)
    p["signatures"].append({"name": body.name or "Anonymous"})
    return {"success": True, "count": len(p["signatures"]), "goal": p["goal"]}

@app.get("/api/bills/{jurisdiction}/{bill_id}")
def api_bill_detail(jurisdiction: str, bill_id: str):
    jur_file = {"CA": "ca_bills.jsonl", "MO": "mo_laws.jsonl", "HK": "hk_bills.jsonl"}
    fname = jur_file.get(jurisdiction)
    if not fname: return JSONResponse({"error": "Unknown jurisdiction"}, status_code=404)
    path = Path(__file__).parent.parent / "output" / fname
    if not path.exists(): return JSONResponse({"error": "Data not found"}, status_code=404)
    with open(path) as f:
        for line in f:
            rec = json.loads(line)
            rid = rec.get("bill_id") or f"MO-{rec.get('law_id', '')}"
            if rid == bill_id: return rec
    return JSONResponse({"error": "Not found"}, status_code=404)

# ── 翻译 endpoint ──
class TranslateRequest(BaseModel):
    texts: list[str]; lang: str = "zh"

@app.post("/api/translate")
def api_translate(body: TranslateRequest):
    """批量翻译英文法案标题为中文。"""
    try:
        import httpx, os
        api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
        base_url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic")
        model = os.environ.get("ANTHROPIC_MODEL", "deepseek-v4-flash")
        texts = body.texts[:20]
        input_text = "\n".join(f"{i+1}. {t}" for i,t in enumerate(texts))
        prompt = f"Translate these bill titles to Chinese. Output each on a new line with the same numbering. Only translate, no explanation.\n\n{input_text}"
        with httpx.Client(timeout=60) as http:
            resp = http.post(f"{base_url}/messages", headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={"model": model, "max_tokens": 2000, "messages": [{"role": "user", "content": prompt}]})
            text = "".join(b.get("text","") for b in resp.json().get("content",[]) if b.get("type")=="text")
        # Parse translations
        lines = text.strip().split("\n")
        trans = {}
        for line in lines:
            m = re.match(r'(\d+)\.\s*(.*)', line.strip())
            if m: trans[int(m.group(1))-1] = m.group(2).strip()
        result = [trans.get(i, texts[i]) for i in range(len(texts))]
        return {"translations": result}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/")
def index():
    html_path = static_dir / "index.html"
    if html_path.exists():
        return HTMLResponse(html_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Leges</h1><p>Frontend not found.</p>")
