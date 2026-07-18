# 小律提案：AI为AI立法

<p align="center">
  <img src="logo.png" width="120" alt="Leges Logo">
</p>

### Leges: One lex at a time

> **AI 帮 AI 立法 —— 让机器 24 小时不停为机器起草法案**

---

## 📖 缘起

AI 立法正在全球范围内加速，但政府无从下手。为加州州众议员实习期间，我发现了一个人民生成法案的缝隙：法案语言太难、门槛太高，普通人的声音很难进入立法程序。

如果用 AI 帮 AI 立法，能否可行？

为了寻找答案，我做了一个**小律提案**。

---

## 🎯 解决的五个问题

| # | 问题 | 解决方案 |
|---|------|---------|
| 1 | **政府无从下手** — AI 立法加速，但没有现成剧本 | **Search Agent**：跨法域搜索数千条法案先例，让立法者站在巨人肩膀上 |
| 2 | **法案语言是壁垒** — 普通人看不懂、写不了法案 | **Generate Agent**：输入主题即可生成专业法案草案，支持三种详细度 |
| 3 | **跨法域信息孤岛** — CA/HK/MO 各自摸索 | **三法域融合**：统一检索加州、香港、澳门数据，一键对比 |
| 4 | **被动立法而非主动立法** — 总在危机后才反应 | **Black Box**：24/7 自主生成 AI 法案，变被动为主动 |
| 5 | **AI 立法不能只靠内部人** — 受影响者无法参与 | **完整参与链**：搜索 → 起草 → 分析 → 请愿 → 社媒，人人可用 |

---

## ✨ 核心亮点

### 1. 人机双轨立法 —— Human + Autonomous 双模式

**人操控的 Agent 链：**
搜索既有法案 → 生成草案 → 分析通过率 → 社媒推广，形成完整的立法倡导闭环。每个 Agent 既可独立使用，也可串联协作。

**纯机器的 Black Box：**
全球首个 24/7 不间断的自主 AI 立法机。无需任何人干预，持续生成 AI 政策法案。

### 2. 跨法域智能 —— 三地数据融合

同时利用加州（两党制）、香港（行政主导）、澳门（行政长官事前同意）三种截然不同的制度环境数据进行检索和生成，形成独特的"制度光谱"研究框架。

### 3. 法案起草透明化

让普通人也能参与立法过程——搜索先例、生成草案、分析成功率、发起请愿、社媒推广，每一步都有 AI 辅助。

---

## 🏗️ 架构设计

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
│   向量嵌入检索 (384-dim embeddings + cosine similarity)    │
└─────────────────────────────────────────────────────────┘
```

### 多智能体协同

| Agent | 角色 | 输入 → 输出 |
|-------|------|------------|
| 🔍 Search | 法案检索 | 自然语言查询 → 相似法案列表（含相关性评分） |
| ✎ Generate | 法案起草 | 主题 + 风格 → 完整法案草案（含议员推荐 + 请愿） |
| 📊 Analysis | 通过率预测 | 法案主题 → 通过率 + 政党倾向 + 图表 |
| 📣 Social | 社媒推广 | 法案信息 → 多平台适配帖子（含请愿 CTA） |
| 📦 Black Box | 自主立法 | 无输入 → 不间断生成 AI 法案（随机主题/法域） |

---

## 🤖 智能体融合与模型优化

### 多智能体协同机制

每个 Agent 独立调用 Deepseek 大模型，通过结构化 Prompt 工程实现专业分工：

- **Search Agent**：利用 384 维向量嵌入进行语义检索，支持中英文混合查询，中文自动翻译为英文后再检索
- **Generate Agent**：三段式 Prompt（角色设定 + 任务描述 + 格式约束），支持标准/详细/简洁三种输出粒度
- **Social Agent**：内置六大文案模板角度（问题-解决方案、热点话题、故事分享、社区互动、进展更新、紧急呼吁），平台风格指南作为 System Prompt 注入
- **Black Box**：25 个 AI 政策主题池随机轮换，3-6 秒间隔持续调用，实现无监督自主生成

### 模型优化

- 通过精确的 Prompt Engineering（角色设定、输出格式约束、语言强制指令）减少幻觉和格式错误
- 语言隔离策略：中英文模式下分别追加强制语言指令，杜绝语言混杂
- 使用 Vercel 无服务器部署，冷启动优化，API 超时 90-120 秒适配长文本生成

---

## 🛠️ 技术栈

| 层 | 技术 | 说明 |
|-------|------|------|
| 后端框架 | Python / FastAPI | 轻量异步 Web 框架 |
| 前端 | 静态 HTML + Vanilla JS | 零依赖，直出渲染 |
| AI 推理 | Deepseek（Anthropic 兼容 API）+ StepFun | Social Agent 和 Black Box 使用 StepFun |
| 向量检索 | NumPy + cosine similarity | 384 维嵌入语义搜索 |
| 部署平台 | Vercel（`@vercel/python`） | 无服务器快速部署 |
| 数据 | 三法域立法语料库 | CA（leginfo）+ HK（LegCo）+ MO |

### 使用的 NVIDIA 及第三方工具

- **NVIDIA SDK**：DGX Spark 平台全栈能力
- **Stepfun 阶跃星辰**：配套大模型支持
- **Deepseek v4**：通过 Anthropic 兼容接口驱动 AI 推理

---

## ⚡ 部署说明

### 本地（DGX Spark）部署

```bash
# 1. 克隆仓库
git clone https://github.com/your-username/leges.git
cd leges

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量
export ANTHROPIC_AUTH_TOKEN="your-api-key"
export ANTHROPIC_BASE_URL="https://api.deepseek.com/anthropic"
export ANTHROPIC_MODEL="deepseek-v4-flash"

# 4. 启动本地服务
uvicorn web.routes:app --host 0.0.0.0 --port 8000

# 5. 访问 http://localhost:8000
```

### 大模型优化

- 利用 DGX Spark 本地算力进行 Prompt 模板缓存，减少重复 API 调用
- 向量嵌入文件（`data/embeddings.npy`）预计算后加载，无需实时推理
- API 调用使用连接复用（httpx Client），减少握手开销

### Vercel 部署

```bash
npm_config_cache=/tmp/npm-cache npx vercel --name leges-app --prod
```

---

## 📁 项目结构

```
├── web/
│   ├── routes.py          # FastAPI 路由（所有 Agent 端点）
│   └── static/
│       └── index.html      # 单页前端
├── engine/
│   └── config.py           # 法域/语言/预设配置
├── data/
│   ├── embeddings.npy      # 法案向量嵌入
│   └── bill_metadata.json  # 法案元数据
├── output/                 # 立法数据文件
├── DESIGN.md               # 设计系统文档
├── pyproject.toml          # Python 项目配置
├── vercel.json             # Vercel 部署配置
└── requirements.txt        # 依赖清单
```

---

## 🎯 评审标准对应

| 标准 | 权重 | 本项目对应 |
|------|------|-----------|
| 实用性、行业落地价值与技术创新性 | 25% | AI 立法填补空白，人机双轨模式创新，跨法域制度光谱研究框架 |
| 智能体融合与模型优化技术深度 | 25% | 5 大 Agent 协同，结构化 Prompt 工程，向量语义检索，24/7 自主生成 |
| 项目完整性 | 20% | 前后端完整、5 个 Agent 全功能可用、i18n 双语、文档详实 |
| 平台适配性 | 15% | DGX Spark 全栈适配，NVIDIA SDK + Stepfun 模型调用 |
| 演示效果 | 10% | 视频展示 5 大 Agent + Black Box 全流程 |
| 赛事征文 | 5% | "十日谈"开发历程记录 |

---

## 🔮 未来路线图

- **自动更新**：Black Box 24/7 全年无休运作，持续为 AI 快速提案
- **定时刷新**：Search / Generate 等模块每数月刷新一次，保持数据与体验的新鲜度
- **多法域扩展**：引入更多司法管辖区的立法数据
- **多 API 接入**：接入更多 LLM API（Social Agent 和 Black Box 已使用 StepFun）

---

## 🎨 设计系统

配色与组件规范详见 [DESIGN.md](DESIGN.md)。

---

## 👥 团队

*（此处置入团队合影）*

---

## 📹 演示视频

*（此处链接演示视频）*

---

## 📄 开源

本项目已开源。欢迎提交 Issue 和 PR。

---

*为 DGX Spark Hackathon 2026 打造 · 「十日谈」开发历程记录*
