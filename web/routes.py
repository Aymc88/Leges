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
        import re
        # 整词匹配,避免 "cat" 匹配 "education"
        patterns = [re.compile(r'\b' + re.escape(w) + r's?\b', re.I) for w in query.lower().split()]
        scored = []
        for m in meta:
            txt = ((m.get("title","") or "") + " " + (m.get("bill_id","") or ""))
            full_matches = sum(1 for p in patterns if p.search(txt))
            if full_matches > 0:
                scored.append((full_matches, m))
        scored.sort(key=lambda x: -x[0])
        return [{"id": m["bill_id"], "score": s/len(patterns), "document": m["title"], "metadata": m} for s,m in scored[:top_k]]
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

@app.get("/api/debug")
def api_debug():
    """Debug search - test search_keyword directly"""
    from web.routes import search_keyword
    results = search_keyword("cat", 10)
    return {"count": len(results), "results": [{"id": r["id"], "jur": r["metadata"]["jurisdiction"], "title": r["metadata"]["title"][:50]} for r in results[:5]]}

@app.post("/api/search")
def api_search(body: SearchRequest):
    try:
        query = body.query
        # 如果查询含非ASCII(中文),先翻译成英文
        if not query.isascii():
            try:
                import httpx, os
                api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN") or "sk-255ecb50a0f84c15b3a6d56fe5269cf0"
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
        results = search_keyword(query, body.top_k * 10)  # 多搜一些,确保覆盖预设过滤
        results = [r for r in results if r.get("metadata",{}).get("jurisdiction") in jur_set] if jur_set else results
        return {"results": results[:body.top_k], "query": body.query}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

class GenerateRequest(BaseModel):
    topic: str; title: str = ""; style: str = "standard"; lang: str = "zh"; analysis: bool = False

SOCIAL_TEMPLATES = {
    "A": {
        "name": "Problem-Solution",
        "name_zh": "问题-解决方案",
        "hook": "Struggling with {topic}? Here's a simple strategy that could help.",
        "hook_zh": "还在为{topic}困扰？这个简单策略或许能帮到你。",
    },
    "B": {
        "name": "Hot Topic Take",
        "name_zh": "热点话题",
        "hook": "Common industry myth about {topic} is making you a fool.",
        "hook_zh": "关于{topic}的行业误区，让你白白走了弯路。",
    },
    "C": {
        "name": "Journey Story",
        "name_zh": "故事分享",
        "hook": "Last year we faced a major challenge with {topic}. Here's what we learned.",
        "hook_zh": "去年我们在{topic}上遇到了大挑战。这是我们的收获。",
    },
    "D": {
        "name": "Community Engagement",
        "name_zh": "社区互动",
        "hook": "We want to hear from you!",
        "hook_zh": "我们想听听你的看法！",
    },
    "E": {
        "name": "Goal Progress",
        "name_zh": "进展更新",
        "hook": "With your help, we've reached a milestone on {topic}!",
        "hook_zh": "有了你的支持，我们在{topic}上达成了新里程碑！",
    },
    "F": {
        "name": "Urgency Call",
        "name_zh": "紧急呼吁",
        "hook": "Calling all supporters! The deadline for {topic} is coming up.",
        "hook_zh": "致所有支持者！{topic}的截止日期快到了。",
    },
}

class SocialPostRequest(BaseModel):
    topic: str
    platforms: list[str]
    angles: list[str] = ["A", "B", "C", "D"]
    lang: str = "en"
    hashtags: list[str] = []
    petition_goal: int = 2000
    petition_signatures: int = 0
    bill_title: str = ""
    campaign_url: str = ""

class SocialPublishRequest(BaseModel):
    topic: str
    platform: str
    content: str
    scheduled_at: str = ""

@app.post("/api/generate")
def api_generate(body: GenerateRequest):
    try:
        import httpx, os
        api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN") or "sk-255ecb50a0f84c15b3a6d56fe5269cf0"
        base_url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic")
        model = os.environ.get("ANTHROPIC_MODEL", "deepseek-v4-flash")
        if not api_key:
            return JSONResponse({"error": "API not configured"}, status_code=500)
        if body.analysis:
            if body.style == "party":
                if body.lang == "zh":
                    prompt = f"分析政党投票率: {body.topic}\n\n请根据该法案主题的性质，估算各法域政党可能支持或反对的比例。输出真实数字（总和100%），不要用 XX。\n\n格式：\n加州: 民主党 XX% 共和党 XX%\n香港: 建制派 XX% 民主派 XX%\n澳门: 亲政府 XX% 其他 XX%\n\n每行一个，只输出百分比，不要解释。"
                else:
                    prompt = f"Party vote analysis for: {body.topic}\n\nBased on this bill topic, estimate the percentage of each party that would support it. Output real numbers (total 100%), NO placeholders.\n\nFormat:\nCA: Democrats XX% Republicans XX%\nHK: Pro-establishment XX% Democrats XX%\nMO: Pro-govt XX% Others XX%\n\nOne per line, percentages only, no explanation."
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

def _build_social_platform_prompt(lang: str) -> str:
    if lang == "zh":
        return """## 平台风格指南

### Instagram（视觉优先、生活化）
- 故事驱动的文案,强钩子开头
- 5-15个标签,清晰的行动号召
- 语气：有抱负的、生活方式的

### LinkedIn（专业权威）
- 行业洞察、问题解决型内容
- 3-5个专业标签
- 语气：专业、有见地、权威

### X/Twitter（简洁尖锐）
- 280字符以内
- 1-2个话题标签
- 语气：犀利、机智、实时

### Facebook（对话社区）
- 适合讨论的长文
- 社区感
- 语气：对话式、以社区为中心

### 小红书（种草价值导向）
- "短、平、快"的阅读习惯
- 侧重提供价值、建立信任和引导互动
- 视觉优先,真实体验分享
- 语气：真诚、实用、种草"""
    return """## Platform Tone Guide

### Instagram (Visual-first, lifestyle)
- Story-driven captions with strong hook
- 5-15 hashtags, clear CTA
- Tone: Aspirational, lifestyle

### LinkedIn (Professional, authoritative)
- Industry insights, problem-solving content
- 3-5 professional hashtags
- Tone: Professional, insightful, authoritative

### X/Twitter (Sharp, witty, real-time)
- Under 280 characters
- 1-2 trending/event hashtags
- Tone: Sharp, witty, concise

### Facebook (Conversational, community)
- Informative posts for discussion
- Community-focused
- Tone: Conversational, community-oriented

### Xiaohongshu (Value-driven, grass-seeding)
- Short, fast-paced reading style
- Focus on value, trust-building, interaction
- Visual-first with authentic experience sharing
- Tone: Sincere, practical, grass-seeding"""

@app.post("/api/social/generate")
def api_social_generate(body: SocialPostRequest):
    try:
        import httpx, os, json
        api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN") or "sk-255ecb50a0f84c15b3a6d56fe5269cf0"
        base_url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic")
        model = os.environ.get("ANTHROPIC_MODEL", "deepseek-v4-flash")
        lang = body.lang
        zh = lang == "zh"

        # Build angle descriptions
        angle_descs = []
        for a in body.angles:
            t = SOCIAL_TEMPLATES.get(a)
            if t:
                hook = t["hook_zh" if zh else "hook"].format(topic=body.topic)
                angle_descs.append(f"{a}: {t['name_zh' if zh else 'name']} — {hook}")
        angle_text = "\n".join(angle_descs) if angle_descs else "A: Problem-Solution — Standard approach"

        platform_guide = _build_social_platform_prompt(lang)
        hashtag_guide = "、".join(body.hashtags) if body.hashtags else (f"#{body.topic.replace(' ', '')}" if lang == "en" else f"#{body.topic}")

        petition_context = ""
        if body.petition_goal:
            pct = round(body.petition_signatures / body.petition_goal * 100) if body.petition_goal else 0
            bill_title = body.bill_title or body.topic
            url = body.campaign_url or "link in bio"
            if zh:
                petition_context = f"""
## 请愿活动背景
- 法案标题：{bill_title}
- 请愿目标：{body.petition_goal} 人支持
- 当前进度：{body.petition_signatures} 人已签名（{pct}%）
- 行动链接：{url}

【核心任务】每条帖子都必须推动读者去签署请愿书支持该法案。
帖子正文要解释为什么这个法案重要、为什么需要公众支持、签名会产生什么影响。
CTA 必须引导用户「点链接签名」或「分享让更多人知道」。"""
            else:
                petition_context = f"""
## Petition Campaign Context
- Bill Title: {bill_title}
- Petition Goal: {body.petition_goal} supporters
- Current Progress: {body.petition_signatures} signed ({pct}%)
- Action URL: {url}

【CORE MISSION】Every post MUST drive readers to sign the petition supporting this bill.
Explain why this bill matters, why public support is needed, and what impact signatures will have.
CTA must direct users to "sign the petition" or "share to spread the word"."""

        if zh:
            prompt = f"""你是一位社会活动倡导专家。你的任务是为一项法案生成请愿推广帖子，目标是动员公众签署请愿书来支持该法案。

## 法案/活动主题
{body.topic}

目标平台：{', '.join(body.platforms)}
标签建议：{hashtag_guide}
{petition_context}

可用文案模板角度（可组合使用）：
{angle_text}

{platform_guide}

## 通用原则
1. 开头两行必须抓住注意力（反常识观点/大胆断言/好奇心缺口）
2. 简洁清晰，避免行话
3. 80/20法则：80%解释法案为何重要+为何需要支持，20%直接呼吁行动
4. 每帖必须有明确的请愿行动号召：引导读者点链接签名

## 每篇帖子的必备要素
- 法案解决的问题（为什么重要）
- 公众支持为什么关键（立法者倾听选民）
- 签名会产生什么影响（数字就是力量）
- 明确的行动号召 → 去签名

请为每个选定的平台生成1-2条帖子文案。
每条帖子需包含：平台名、文案正文（含换行）、推荐标签（3-5个）、CTA。

用以下格式输出（不要额外解释）：

=== [平台名] ===
[帖子文案正文]

标签： [标签列表]
CTA： [行动号召]

重要：所有帖子必须用中文撰写，包括 Instagram、LinkedIn、X/Twitter、Facebook 等海外平台。不得出现英文。
---"""
        else:
            prompt = f"""You are a social advocacy campaign strategist. Your mission is to generate petition-drive posts for a bill — every post must drive people to sign the petition supporting it.

## Campaign Topic
{body.topic}

Target Platforms: {', '.join(body.platforms)}
Suggested hashtags: {hashtag_guide}
{petition_context}

Available template angles (combinable):
{angle_text}

{platform_guide}

## General Rules
1. First two lines must stop the scroll (contrarian take / bold claim / curiosity gap)
2. Keep it clear and brief — no jargon
3. 80/20 rule: 80% explaining why the bill matters + why support is needed, 20% direct call to action
4. Every post MUST have a petition-focused CTA: drive readers to sign

## Every Post Must Include
- The problem this bill solves (why it matters)
- Why public support is critical (legislators listen to constituents)
- What impact signatures have (numbers = power)
- Clear call to action → go sign

Generate 1-2 post drafts per selected platform.
Each post must include: platform name, post body (with line breaks), recommended hashtags (3-5), and CTA.

Use this format (no extra explanation):

=== [Platform Name] ===
[Post body text here]

Hashtags: [list]
CTA: [call to action]
---

IMPORTANT: ALL posts must be written in English ONLY, including for Xiaohongshu. Never use Chinese, even for Chinese platforms."""

        with httpx.Client(timeout=120) as http:
            resp = http.post(f"{base_url}/messages", headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={"model": model, "max_tokens": 3000, "messages": [{"role": "user", "content": prompt}]})
            text = "".join(b.get("text","") for b in resp.json().get("content",[]) if b.get("type")=="text")

        # Parse structured results
        import re
        platforms_out = {}
        current_platform = "General"
        current_parts = []
        for line in text.strip().split("\n"):
            m = re.match(r'===\s*(.+?)\s*===', line)
            if m:
                if current_parts:
                    platforms_out[current_platform] = "\n".join(current_parts).strip()
                current_platform = m.group(1).strip()
                current_parts = []
            elif line.strip() == "---":
                continue
            else:
                current_parts.append(line)
        if current_parts:
            platforms_out[current_platform] = "\n".join(current_parts).strip()

        return {"success": True, "topic": body.topic, "posts": platforms_out, "raw": text}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

# ── AI Black Box — Autonomous Bill Generation ──

AI_BILL_TOPICS = [
    "AI Safety Standards and Testing Requirements",
    "Autonomous Vehicle Liability and Insurance Framework",
    "AI in Healthcare Diagnostics Regulation",
    "Social Media Content Moderation Transparency Act",
    "Algorithmic Bias Prevention and Fairness Standards",
    "AI Data Privacy and Consent Management",
    "AI in Employment and Hiring Decisions Regulation",
    "Synthetic Media and Deepfake Labeling Requirements",
    "AI Research Funding and Ethics Oversight",
    "AI in Criminal Justice Risk Assessment Reform",
    "AI Energy Consumption and Environmental Impact Disclosure",
    "AI-Generated Intellectual Property Rights Reform",
    "AI in Education Personalized Learning Standards",
    "Government Use of Facial Recognition Technology Moratorium",
    "AI Systems Audit and Accountability Requirements",
    "Child Safety and Age Verification in AI Systems",
    "AI in Financial Services Risk Management",
    "Robotics and AI Labor Displacement Compensation Fund",
    "International AI Treaty and Cooperation Framework",
    "AI Military Applications and Autonomous Weapons Control",
    "AI Election Interference Prevention Act",
    "AI Transparency and Explainability Standards",
    "AI in Housing and Tenant Screening Regulation",
    "AI Watermarking and Content Authentication Act",
    "AI Digital Personhood and Legal Liability Framework",
]

class BlackBoxRequest(BaseModel):
    topic: str = ""
    lang: str = "en"

@app.post("/api/blackbox/generate")
def api_blackbox_generate(body: BlackBoxRequest):
    try:
        import httpx, os, random, json, re, time
        api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN") or "sk-255ecb50a0f84c15b3a6d56fe5269cf0"
        base_url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic")
        model = os.environ.get("ANTHROPIC_MODEL", "deepseek-v4-flash")

        topic = body.topic if body.topic else random.choice(AI_BILL_TOPICS)
        jurisdiction = random.choice(["CA", "HK", "MO"])
        zh = body.lang == "zh"

        if zh:
            prompt = f"""你是一位AI政策智库的立法起草专家。请生成一份关于AI监管的完整、详细法案。

主题：{topic}
法域：{jurisdiction}

格式：
第一行仅限法案标题（如"2026年AI安全标准法案"）
空一行，然后是完整的法案正文。

法案必须包含：
- 序言/鉴于条款
- 关键条款（编号章节）
- 执行机制
- 违规处罚
- 资金条款

内容需现实、具体、有说服力，400-800字。仅输出中文，不得出现英文。"""
        else:
            prompt = f"""You are a legislative drafter at an AI policy think tank. Generate a complete, detailed bill about AI regulation.

Topic: {topic}
Jurisdiction: {jurisdiction}

Format:
First line is the bill title only (e.g. "AI Safety Standards Act of 2026")
Then a blank line, then the full bill text.

The bill must include:
- Preamble/whereas clauses
- Key provisions (numbered sections)
- Enforcement mechanisms
- Penalties for violations
- Funding provisions

Make it realistic, specific, compelling, and 400-800 words. Output in English only."""

        with httpx.Client(timeout=90) as http:
            resp = http.post(f"{base_url}/messages", headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={"model": model, "max_tokens": 3000, "messages": [{"role": "user", "content": prompt}]})
            text = "".join(b.get("text","") for b in resp.json().get("content",[]) if b.get("type")=="text")

        # Extract title from first line
        lines = text.strip().split("\n")
        title = lines[0].strip() if lines else topic
        title = title.replace("**", "").replace("__", "").replace("#", "").strip()
        content = "\n".join(lines[1:]).strip() if len(lines) > 1 else text

        bill_id = f"AI-{jurisdiction}-{random.randint(1000, 9999)}"

        return {
            "success": True,
            "bill": {
                "id": bill_id,
                "jurisdiction": jurisdiction,
                "topic": topic,
                "title": title,
                "content": content,
                "generated_at": int(time.time()),
            }
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

class LegislatorRequest(BaseModel):
    topic: str; jurisdiction: str = "CA"; lang: str = "en"

@app.post("/api/legislators")
def api_legislators(body: LegislatorRequest):
    try:
        import httpx, json, re, os
        api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN") or "sk-255ecb50a0f84c15b3a6d56fe5269cf0"
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
        api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN") or "sk-255ecb50a0f84c15b3a6d56fe5269cf0"
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
