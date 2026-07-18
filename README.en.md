# Leges: One lex at a time

<p align="center">
  <img src="logo.png" width="120" alt="Leges Logo">
</p>

### AI legislating for AI — machines drafting laws for machines, 24/7

---

## 📖 Origin

AI legislation is accelerating worldwide, but governments don't know where to start. During my internship with a California State Assemblymember, I discovered a gap in the legislative process: the language of bills is too complex, the barrier too high for ordinary people to participate.

Can AI legislate for AI?

To answer that, I built **Leges**.

---

## 🎯 Five Problems — Five Solutions

| # | Problem | Solution |
|---|---------|----------|
| 1 | **Governments don't know where to start** — AI legislation is accelerating with no playbook | **Search Agent**: Cross-jurisdictional search across thousands of bills — legislators stand on giants' shoulders |
| 2 | **Bill language is a barrier** — Ordinary people can't read or write legislation | **Generate Agent**: Input a topic, get a professional bill draft in 3 levels of detail |
| 3 | **Cross-jurisdictional silos** — CA/HK/MO each figuring it out alone | **Tri-jurisdiction fusion**: Unified search across California, Hong Kong, and Macau data |
| 4 | **Reactive, not proactive** — Legislators only act after a crisis | **Black Box**: 24/7 autonomous AI bill generation — turning reactive into proactive |
| 5 | **AI policy can't be insider-only** — The affected have no voice | **Full participation chain**: Search → Draft → Analyze → Petition → Social — for everyone |

---

## ✨ Key Highlights

### 1. Dual-Mode Legislation — Human + Autonomous

**Human-driven Agent pipeline:**
Search existing bills → Generate draft → Analyze pass rates → Social campaign — a complete legislative advocacy loop. Each Agent works standalone or in sequence.

**Autonomous Black Box:**
The world's first 24/7 non-stop AI legislation engine. Zero human intervention, continuously generating AI policy bills.

### 2. Cross-Jurisdictional Intelligence

Simultaneously leverages three fundamentally different institutional environments — California (bipartisan competition), Hong Kong (executive-led), and Macau (prior written approval by the Chief Executive) — for retrieval and generation, forming a unique **institutional spectrum** research framework.

### 3. Legislative Transparency

Empowering ordinary people to participate in the legislative process — search precedents, draft bills, analyze success rates, launch petitions, promote via social media — every step AI-assisted.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     Web UI (HTML+JS)                     │
├─────────────────────────────────────────────────────────┤
│                   FastAPI Backend                        │
├──────────┬──────────┬──────────┬──────────┬─────────────┤
│  Search  │ Generate │ Analysis │  Social  │  Black Box  │
│  Agent   │  Agent   │  Agent   │  Agent   │   (Auto)    │
├──────────┴──────────┴──────────┴──────────┴─────────────┤
│              Deepseek API (Anthropic-compatible)         │
├─────────────────────────────────────────────────────────┤
│          Legislative Corpora (CA / HK / MO)              │
│    Vector Embedding Search (384-dim + cosine similarity) │
└─────────────────────────────────────────────────────────┘
```

### Multi-Agent Collaboration

| Agent | Role | Input → Output |
|-------|------|---------------|
| 🔍 Search | Bill retrieval | Natural language → Similar bills with relevance scores |
| ✎ Generate | Bill drafting | Topic + style → Full draft + legislator recommendations + petition |
| 📊 Analysis | Pass rate prediction | Bill topic → Pass rate % + party breakdown + chart |
| 📣 Social | Social campaign | Bill info → Platform-adapted posts with petition CTA |
| 📦 Black Box | Autonomous legislation | No input → Continuous AI bill generation |

---

## 🤖 Agent Integration & Model Optimization

### Multi-Agent Coordination

Each Agent independently calls the Deepseek LLM via structured prompt engineering:

- **Search Agent**: 384-dim vector embeddings for semantic retrieval; auto-translates Chinese queries to English
- **Generate Agent**: Three-part prompts (role + task + format constraints) with Standard/Detailed/Simple output levels
- **Social Agent**: 6 template angles (problem-solution, hot topic, journey story, community, goal progress, urgency); platform tone guides injected as system prompts
- **Black Box**: 25 AI policy topics in a rotating pool; 3-6 second intervals for unsupervised autonomous generation

### Optimization

- Precise prompt engineering (role setting, output format, language enforcement) reduces hallucinations
- Language isolation: English/Chinese modes each have forced language directives to prevent code-switching
- Vercel serverless deployment with optimized cold starts and 90-120s API timeouts for long-form generation

---

## 🛠️ Tech Stack

| Layer | Tech | Notes |
|-------|------|-------|
| Backend | Python / FastAPI | Lightweight async web framework |
| Frontend | Static HTML + Vanilla JS | Zero dependencies, direct rendering |
| AI Inference | Deepseek (Anthropic-compatible API) + StepFun | Social Agent & Black Box use StepFun |
| Vector Search | NumPy + cosine similarity | 384-dim semantic bill search |
| Deployment | Vercel (`@vercel/python`) | Serverless rapid deployment |
| Data | 3-jurisdiction legislative corpora | CA (leginfo) + HK (LegCo) + MO |

### NVIDIA & Third-Party Tools

- **NVIDIA SDK**: Full DGX Spark platform integration
- **Stepfun 阶跃星辰**: Companion LLM support
- **Deepseek v4**: AI inference via Anthropic-compatible API

---

## ⚡ Deployment

### Local (DGX Spark)

```bash
# 1. Clone
git clone https://github.com/your-username/leges.git
cd leges

# 2. Install
pip install -r requirements.txt

# 3. Configure
export ANTHROPIC_AUTH_TOKEN="your-api-key"
export ANTHROPIC_BASE_URL="https://api.deepseek.com/anthropic"
export ANTHROPIC_MODEL="deepseek-v4-flash"

# 4. Launch
uvicorn web.routes:app --host 0.0.0.0 --port 8000

# 5. Open http://localhost:8000
```

### LLM Optimization on DGX Spark

- Prompt template caching reduces redundant API calls
- Pre-computed vector embeddings (`data/embeddings.npy`) loaded at startup — no real-time inference needed
- HTTP connection reuse (httpx Client) minimizes handshake overhead

### Vercel Deployment

```bash
npm_config_cache=/tmp/npm-cache npx vercel --name leges-app --prod
```

---

## 📁 Project Structure

```
├── web/
│   ├── routes.py          # FastAPI routes (all Agent endpoints)
│   └── static/
│       └── index.html      # Single-page frontend
├── engine/
│   └── config.py           # Jurisdiction/language/preset config
├── data/
│   ├── embeddings.npy      # Bill vector embeddings
│   └── bill_metadata.json  # Bill metadata index
├── output/                 # Legislative data files
├── DESIGN.md               # Design system documentation
├── pyproject.toml          # Python project config
├── vercel.json             # Vercel deployment config
└── requirements.txt        # Dependencies
```

---

## 🎯 Judging Criteria

| Criterion | Weight | Our Approach |
|-----------|--------|-------------|
| Practicality, Industry Value & Innovation | 25% | AI legislation fills a real gap; dual-mode (human/auto) innovation; cross-jurisdictional institutional spectrum framework |
| Agent Integration & Model Optimization | 25% | 5 Agents in collaboration; structured prompt engineering; vector semantic search; 24/7 autonomous generation |
| Project Completeness | 20% | Full frontend + backend; all 5 Agents functional; i18n bilingual; comprehensive documentation |
| Platform Adaptation | 15% | DGX Spark full-stack; NVIDIA SDK + Stepfun model integration |
| Demo Quality | 10% | Video showcasing all 5 Agents + Black Box end-to-end |
| Written Record | 5% | "Ten Days Talk" development journey |

---

## 🔮 Roadmap

- **Always-on**: Black Box runs 24/7, continuously proposing AI legislation
- **Periodic refresh**: Search / Generate modules refresh every few months with new data and UX
- **Multi-jurisdiction**: Expand to more legislative bodies
- **Multi-API integration**: Support more LLM APIs (Social Agent & Black Box already use StepFun)

---

## 🎨 Design System

Full color palette and component specs in [DESIGN.md](DESIGN.md).

---

## 👥 Team

*(Team photo goes here)*

---

## 📹 Demo Video

*(Demo video link goes here)*

---

## 📄 Open Source

This project is open source. Issues and PRs welcome.

---

*Built for DGX Spark Hackathon 2026 · "Ten Days Talk" Development Chronicle*
