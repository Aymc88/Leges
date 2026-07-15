# Leges — Multi-Jurisdictional Legal Proposal AI Platform

> NVIDIA DGX Spark Hackathon 2026 | Hong Kong · Macau · California
> *Leges: one ledge at a time.*

Leges is a **multi-jurisdictional, multi-lingual legal AI platform** combining semantic search,
AI-assisted drafting, passage-outcome prediction, and public advocacy for legislative research.

**Research framing** — *Cross-jurisdictional legislative predictability*: Hong Kong's legislative
structure shares certain features with common-law systems, making California a meaningful
comparison. Macau extends the system's practical coverage. Comparing jurisdictions with
different institutional designs lets us ask: **how much of a bill's fate is decided by its
content, and how much by the political system it lives in?**

---

## Features

### 🔍 Semantic Search
Cross-jurisdiction statute and case law search via vector similarity, multi-language.

### 📝 AI Draft Generation
Generate legislative bill drafts from a topic description (standard / detailed / concise).

### 📊 Proposal Analysis
Predict passage probability with supporting factors, opposing factors, and similar precedents.
Attribution splits the prediction into **content factors** vs **political factors**.

### 📜 Legislator Proposals & Signatures
- Designate generated drafts as **legislator proposals**
- Public can **sign to show support**, with live signature counts
- Support/oppose sentiment visualized as an aggregate — civic participation, not wagering

### 🤖 AI Proposal Tracker
Track AI-related legislative proposals across jurisdictions: scan, track, report, submit.

---

## Jurisdictions & Languages

| Jurisdiction | Interface / Output Languages | Source-text Language(s) | Prediction |
|---|---|---|---|
| **Hong Kong (HKSAR)** | English · 简体中文 · 繁體中文 | English, 繁體中文 | ⚠️ pending validation |
| **Macau (MSAR)** | English · 简体中文 · 繁體中文 · **Português** | 繁體中文, Português | ⚠️ pending validation |
| **California (USA)** | English · 简体中文 · 繁體中文 · **Español** · **Filipino** | English only | ✅ validated |

**Why Spanish and Filipino for California**: California has large Spanish- and Filipino-speaking
communities. There is **no Spanish/Filipino version of California bills** — these languages exist
in Leges so **advocacy content can be translated** for those communities to read and sign.
That's the point: proposals need public signatures, and people sign what they can read.
*(Status: es/fil translation not yet implemented.)*

**Prediction readiness**: California's AB/SB corpus has verified pass/fail labels
(`chaptered` = passed; `died`/`vetoed` = failed) with a healthy positive/negative balance.
Hong Kong and Macau are **not yet validated** — government bills may pass at near-100% rates,
which would collapse the classification task. Run `verify_hk_data.py` before enabling prediction
for HK. If failure samples are too few, HK/MO serve as **retrieval and comparison** jurisdictions
rather than prediction targets — and *that finding is itself a research result.*

---

## Jurisdiction Display Presets

The backend **always processes all jurisdictions**. Presets control only **what the frontend shows**.

| Preset | Shows | Default language | Use |
|---|---|---|---|
| `hackathon` | HK · MO | 简体中文 | DGX Spark Hackathon |
| `california` | CA | English | California legislative coursework |
| `china` | HK · MO | 简体中文 | Hong Kong & Macau legislative display |

Switch by editing one line in `engine/config.py`:

```python
ACTIVE_PRESET = "hackathon"   # → "california" or "china"
```

Or at runtime: `get_active_config(preset="california")`.

| Key | Action |
|---|---|
| `Ctrl+1` | Hackathon preset (HK/MO) |
| `Ctrl+2` | California preset (California) |
| `Ctrl+3` | China preset (HK/MO) |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI + Uvicorn |
| AI orchestration | Main Agent + Sub-Agent architecture |
| Semantic search | ChromaDB + Sentence Transformers |
| LLM | Anthropic Claude API; SGLang for model serving |
| Frontend | Vanilla HTML/CSS/JavaScript |
| i18n | Built-in multi-language support (en / zh-Hans / zh-Hant / pt / es / fil) |

---

## Quick Start

```bash
pip install -e .

# Seed data
leges-seed-hk        # Hong Kong (Simplified Chinese)
leges-seed-hk-en     # Hong Kong (English)
leges-seed-mo-zh     # Macau (Simplified Chinese)
leges-seed-ca-zh     # California (Simplified Chinese)

# Validate HK data before enabling prediction
python verify_hk_data.py

# Import California AB/SB corpus
python import_ab_sb.py --all

# Run
leges-web            # or: uvicorn web.routes:app --reload --port 8080
leges-mcp            # MCP server
```

Open **http://localhost:8080**

---

## Project Structure

```
leges/
├── engine/
│   ├── config.py       # Jurisdictions, languages, display presets
│   ├── main_agent.py   # Orchestrator
│   ├── commands.py     # Operation registry
│   ├── agents/         # Sub-agents (prediction, creative, social)
│   └── resolvers/      # Analyzers
├── server/
│   ├── mcp_server.py
│   └── tools/          # Search, charts, documents
├── data/               # Corpus + seed data (gitignored)
├── web/
│   ├── routes.py
│   └── static/
└── tests/
```

---

## Architecture Principles

1. **Sub-Agent ≠ Tool** — sub-agents carry LLM reasoning; tools are deterministic mappings.
2. **Unified registry** — capabilities register via `commands.py`, transparent to callers.
3. **Display ≠ data** — presets hide jurisdictions from the UI; the backend still runs them all.
4. **Graceful fallback** — degrades to template data when LLM / vector store is unavailable.
5. **Honest claims** — a jurisdiction is marked `prediction_ready` only after its
   positive/negative sample balance is verified. Unvalidated jurisdictions do retrieval, not prediction.

---

## Bottom-layer Skills

Deliberately **deferred to the end of the project**. Skills encode *lessons already learned*;
writing them before the pipeline runs would mean inventing rules for work not yet done.
Build first, extract the practice, then codify.
