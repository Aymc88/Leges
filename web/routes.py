"""
web/routes.py — Leges FastAPI Web App

Endpoints:
  GET  /api/config           当前配置
  GET  /api/presets          所有预设
  POST /api/config/preset    切换预设  {"preset": "california"}
  POST /api/search           搜索法案  {"query": "...", "jurisdiction": "CA", "top_k": 10}
  GET  /api/bills/{jurisdiction}/{bill_id}  法案详情
  GET  / → web/static/index.html
"""

from __future__ import annotations
import os, json, sys
from pathlib import Path
os.environ.setdefault("HF_HUB_OFFLINE", "1")
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# 确保 leges 项目在路径中
sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.config import (
    get_active_config,
    PRESETS,
    ACTIVE_PRESET,
    JURISDICTIONS,
    LANGUAGES,
    all_jurisdictions,
)

app = FastAPI(title="Leges", version="2.0.0")

# ── 轻量搜索:预计算向量(5MB) + numpy + HuggingFace API ──
_current_preset = "hackathon"
_embeddings = None
_metadata = None
_emb_dim = 384

def load_embeddings():
    global _embeddings, _metadata
    if _embeddings is None:
        try:
            import numpy as np
            data_dir = Path(__file__).parent.parent / "data"
            _embeddings = np.load(str(data_dir / "embeddings.npy"))
            import json
            with open(data_dir / "bill_metadata.json") as f:
                _metadata = json.load(f)
        except Exception:
            _embeddings = []
            _metadata = []
    return _embeddings, _metadata

def embed_query(query: str) -> list[float] | None:
    """将查询转为向量。先试 HuggingFace API,不行就试本地模型。"""
    import httpx, os, sys
    # 方法1: HuggingFace Inference API
    hf_token = os.environ.get("HF_TOKEN", "")
    headers = {"Content-Type": "application/json"}
    if hf_token:
        headers["Authorization"] = f"Bearer {hf_token}"
    try:
        resp = httpx.post(
            "https://api-inference.huggingface.co/pipeline/feature-extraction/sentence-transformers/all-MiniLM-L6-v2",
            json={"inputs": query, "options": {"wait_for_model": True}},
            headers=headers,
            timeout=60,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data and isinstance(data, list):
                vec = data[0] if data and isinstance(data[0], list) else data
                if vec and len(vec) == _emb_dim:
                    return vec
    except Exception:
        pass
    # 方法2: 本地 SentenceTransformer (如果在 DGX Spark 上)
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("all-MiniLM-L6-v2")
        vec = model.encode([query])[0].tolist()
        return vec
    except Exception:
        pass
    return None

# ── 静态文件 ──
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# ── 请求模型 ──
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
    return {
        "presets": {
            k: {
                "key": v.key,
                "label_en": v.label_en,
                "label_zh": v.label_zh,
                "jurisdictions": v.jurisdictions,
                "default_language": v.default_language,
            }
            for k, v in PRESETS.items()
        },
        "active": ACTIVE_PRESET,
    }


@app.post("/api/config/preset")
def api_set_preset(body: PresetSwitch):
    """切换显示预设(临时切换,不影响 settings.json)。"""
    global _current_preset
    key = body.preset
    if key not in PRESETS:
        return JSONResponse({"error": f"未知预设: {key}"}, status_code=400)
    _current_preset = key
    import engine.config as cfg_mod
    cfg_mod.ACTIVE_PRESET = key
    cfg = get_active_config()
    return {"preset": key, "config": cfg.to_dict()}


# ── API: 搜索 ──
@app.post("/api/search")
def api_search(body: SearchRequest):
    """跨法域语义搜索。"""
    try:
        import numpy as np
        embeddings, metadata = load_embeddings()
        if not len(embeddings):
            return JSONResponse({"results": [], "query": body.query, "note": "Search data not loaded."})

        # 嵌入查询
        query_vec = embed_query(body.query)
        if query_vec is None:
            return JSONResponse({"results": [], "query": body.query, "note": "Embedding API unavailable. Try again later."})

        query_arr = np.array(query_vec, dtype=np.float32)

        # 计算余弦相似度
        norms = np.linalg.norm(embeddings, axis=1)
        emb_normed = embeddings / norms.reshape(-1, 1)
        query_norm = np.linalg.norm(query_arr)
        if query_norm > 0:
            query_arr = query_arr / query_norm
        scores = np.dot(emb_normed, query_arr)

        # 按法域过滤
        if body.jurisdiction:
            jur_set = {body.jurisdiction}
        else:
            active_cfg = get_active_config()
            jur_set = set(j.code for j in active_cfg.jurisdictions)

        # 获取匹配结果
        scored = [(float(scores[i]), metadata[i]) for i in range(len(scores))
                  if metadata[i].get("jurisdiction") in jur_set]
        scored.sort(key=lambda x: -x[0])

        results = []
        for score, meta in scored[:body.top_k]:
            results.append({
                "id": meta["bill_id"],
                "score": score,
                "document": meta.get("title", ""),
                "metadata": meta,
            })

        return {"results": results, "query": body.query}

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── 签名请愿(内存存储) ──
_petitions: dict[str, dict] = {}
_petition_id_counter = 0

class PetitionCreateRequest(BaseModel):
    title: str
    topic: str
    goal: int = 2000


class PetitionSignRequest(BaseModel):
    petition_id: str
    name: str = ""



@app.post("/api/petition/create")
def api_petition_create(body: PetitionCreateRequest):
    global _petition_id_counter
    _petition_id_counter += 1
    pid = f"pet-{_petition_id_counter}"
    _petitions[pid] = {
        "id": pid,
        "title": body.title,
        "topic": body.topic,
        "goal": body.goal,
        "signatures": [],
        "created": str(__import__("datetime").datetime.now()),
    }
    return {"success": True, "petition": _petitions[pid]}


@app.get("/api/petition/{petition_id}")
def api_petition_get(petition_id: str):
    p = _petitions.get(petition_id)
    if not p:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return {
        "id": p["id"],
        "title": p["title"],
        "topic": p["topic"],
        "goal": p["goal"],
        "count": len(p["signatures"]),
        "signatures": p["signatures"][-20:],
    }


@app.post("/api/petition/sign")
def api_petition_sign(body: PetitionSignRequest):
    p = _petitions.get(body.petition_id)
    if not p:
        return JSONResponse({"error": "Petition not found"}, status_code=404)
    p["signatures"].append({"name": body.name or "Anonymous", "time": str(__import__("datetime").datetime.now())})
    return {"success": True, "count": len(p["signatures"]), "goal": p["goal"]}


class GenerateRequest(BaseModel):
    topic: str
    title: str = ""
    style: str = "standard"
    lang: str = "zh"
    analysis: bool = False


# ── API: 生成法案 ──
@app.post("/api/generate")
def api_generate(body: GenerateRequest):
    """使用 LLM 生成法案草案。"""
    try:
        import httpx

        api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
        base_url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic")
        model = os.environ.get("ANTHROPIC_MODEL", "deepseek-v4-flash")

        if not api_key:
            return JSONResponse({"error": "API key not configured"}, status_code=500)

        if body.analysis:
            if body.lang == "zh":
                prompt = f"你是一位立法分析师。请分析以下法案主题的通过可能性。\n\n主题: {body.topic}\n\n请给出:\n1. 估计通过率 (0-100%)\n2. 各政党投票倾向（列出 CA/HK/MO 的主要政党及其立场）\n3. 支持因素 (2-3条)\n4. 反对因素 (2-3条)\n5. 最适合提出该法案的法域 (加州/香港/澳门) 及原因\n\n简明扼要，3-5句话。"
            else:
                prompt = f"You are a legislative analyst in our multi-jurisdiction system. Analyze the passage likelihood for this bill topic.\n\nTopic: {body.topic}\n\nJurisdiction codes: CA=California(USA), HK=Hong Kong SAR(China), MO=Macau SAR(China). These are the ONLY three. MO is Macau, NOT Missouri.\n\nProvide:\n1. Estimated pass rate (0-100%)\n2. Party breakdown - for EACH jurisdiction, list the major parties and whether they'd likely support or oppose (CA: Democrats/Republicans; HK: DAB/Demo/Liberal; MO: UGM/alliance)\n3. Supporting factors (2-3)\n4. Opposing factors (2-3)\n5. Best jurisdiction (CA/HK/MO only) to propose this and why\n\nBe concise, 4-6 sentences."
        else:
            style_guide = {"standard": "", "detailed": "请写得非常详细，每一条款展开说明，包含子条款和法律依据。总长度800-1500字。", "simple": "请写得简短精炼，每条用1-2句话概括。总长度200-400字。"}
            if body.lang == "zh":
                base = f"你是一位立法助理。请根据以下信息生成一份法案草案。\n\n标题: {body.title or '（未命名）'}\n主题描述: {body.topic}\n"
                base += style_guide.get(body.style, "")
                base += "\n\n请按照以下结构生成:\n1. 法案名称\n2. 立法目的\n3. 关键条款\n4. 实施机制\n5. 预期影响\n\n使用正式、清晰的法律语言。输出应为中文。"
                prompt = base
            else:
                en_guide = {"standard": "", "detailed": "Be very detailed. Expand each provision with sub-clauses and legal reasoning. Total length 800-1500 words.", "simple": "Be concise. Summarize each section in 1-2 sentences. Total length 200-400 words."}
                base = f"You are a legislative drafter. Generate a bill draft based on the following.\n\nTitle: {body.title or '(Untitled)'}\nTopic: {body.topic}\n"
                base += en_guide.get(body.style, "")
                base += "\n\nFollow this structure:\n1. Bill title\n2. Legislative purpose\n3. Key provisions\n4. Implementation mechanism\n5. Expected impact\n\nUse formal, clear legal language. Output MUST be in English."
                prompt = base

        with httpx.Client(timeout=60) as http:
            resp = http.post(
                f"{base_url}/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": 2000,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            data = resp.json()
            generated_text = ""
            if "content" in data and len(data["content"]) > 0:
                for block in data["content"]:
                    if block.get("type") == "text":
                        generated_text += block["text"]

        return {
            "success": True,
            "generated": generated_text or "No content generated",
            "title": body.title or body.topic[:50],
        }

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


class LegislatorRequest(BaseModel):
    topic: str
    jurisdiction: str = "CA"
    lang: str = "en"


# ── API: 寻找支持议员 ──
@app.post("/api/legislators")
def api_legislators(body: LegislatorRequest):
    """使用 LLM 推荐可能支持该法案的议员。"""
    try:
        import httpx
        api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
        base_url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic")
        model = os.environ.get("ANTHROPIC_MODEL", "deepseek-v4-flash")

        if not api_key:
            return JSONResponse({"error": "API key not configured"}, status_code=500)

        jur_names = {"CA": "California", "HK": "Hong Kong", "MO": "Macau"}

        if body.lang == "zh":
            prompt = f"你是一位立法分析师。请根据以下法案主题，推荐3-5位可能支持该法案的{jur_names.get(body.jurisdiction, body.jurisdiction)}议员。\n\n法案主题: {body.topic}\n\n对每位议员，请提供:\n1. 姓名\n2. 所在议院/委员会\n3. 选区\n4. 政党\n5. 支持理由（结合其历史立场和委员会角色）\n\n以JSON数组格式输出，每个元素包含 name, chamber, district, party, reason 字段。仅输出JSON，不要其他文字。"
        else:
            prompt = f"You are a legislative analyst. Based on the following bill topic, recommend 3-5 legislators in {jur_names.get(body.jurisdiction, body.jurisdiction)} who would likely support this bill.\n\nTopic: {body.topic}\n\nFor each legislator, provide:\n1. Name\n2. Chamber/Committee\n3. District\n4. Party affiliation\n5. Reason for support (based on their known positions and committee roles)\n\nOutput as a JSON array, each element with fields: name, chamber, district, party, reason. Output ONLY valid JSON, no other text."

        with httpx.Client(timeout=60) as http:
            resp = http.post(
                f"{base_url}/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": 2000,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            data = resp.json()
            text = ""
            if "content" in data and len(data["content"]) > 0:
                for block in data["content"]:
                    if block.get("type") == "text":
                        text += block["text"]

            # Parse JSON from the response
            import re
            json_match = re.search(r'\[.*\]', text, re.DOTALL)
            legislators = []
            if json_match:
                legislators = json.loads(json_match.group())

        return {"success": True, "legislators": legislators, "topic": body.topic}

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── API: 法案详情(从 JSONL 读取) ──
@app.get("/api/bills/{jurisdiction}/{bill_id}")
def api_bill_detail(jurisdiction: str, bill_id: str):
    jur_file = {"CA": "ca_bills.jsonl", "MO": "mo_laws.jsonl", "HK": "hk_bills.jsonl"}
    fname = jur_file.get(jurisdiction)
    if not fname:
        return JSONResponse({"error": f"未知法域: {jurisdiction}"}, status_code=404)

    path = Path(__file__).parent.parent / "output" / fname
    if not path.exists():
        return JSONResponse({"error": "数据文件不存在"}, status_code=404)

    with open(path) as f:
        for line in f:
            rec = json.loads(line)
            rid = rec.get("bill_id") or f"MO-{rec.get('law_id', '')}"
            if rid == bill_id:
                return rec
    return JSONResponse({"error": "未找到"}, status_code=404)


# ── SPA 入口 ──
@app.get("/")
def index():
    html_path = static_dir / "index.html"
    if html_path.exists():
        return HTMLResponse(html_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Leges — 前端待建</h1><p>请创建 web/static/index.html</p>")


# ── 直接运行 ──
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
