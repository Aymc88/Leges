"""
engine/config.py — 法域 / 语言 / 显示切换配置

核心设计:
    后端【所有法域的数据和模型照常跑】,
    只有当前预设里的法域会在【前端显示】。
    → 改一行就能切换展示重点,数据不受影响。

★ 制度光谱(本项目的核心研究框架):
    三个法域恰好代表"制度约束"从弱到强的三档 ——
      CA(加州) 党派竞争激烈,大量法案失败    → 内容+政治都影响,可预测
      HK(香港) 政府主导,通过率偏高            → 制度影响更大,待验证
      MO(澳门) 议案需行政长官事先书面同意      → 筛选发生在提案【之前】,
                                                预测任务结构上不成立
    核心洞察:当制度筛选发生在提案之前,"预测通过率"这个问题本身就消失了 ——
    因为失败的提案从未被提出。

用法:
    from engine.config import get_active_config, PRESETS
    cfg = get_active_config()                    # 用当前 ACTIVE_PRESET
    cfg = get_active_config(preset="study")      # 临时切成加州
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal

JurisdictionCode = Literal["HK", "MO", "CA"]

# 法域在系统里承担的角色
Role = Literal[
    "prediction",   # 可做通过率预测(正负样本齐全)
    "retrieval",    # 仅做检索 / 对比(样本不支持预测)
    "control",      # 制度对照组(预测任务结构上不成立)
]


# ══════════════════════════════════════════════════════════
# API 来源
# ══════════════════════════════════════════════════════════
# Stepfun API — 通过环境变量 STEPFUN_API_KEY 注入

# ══════════════════════════════════════════════════════════
# 语言
# ══════════════════════════════════════════════════════════
@dataclass(frozen=True)
class Language:
    code: str
    name_en: str
    name_native: str


LANGUAGES: dict[str, Language] = {
    "en":      Language("en",      "English",             "English"),
    "zh-Hans": Language("zh-Hans", "Simplified Chinese",  "简体中文"),
    "zh-Hant": Language("zh-Hant", "Traditional Chinese", "繁體中文"),
    "pt":      Language("pt",      "Portuguese",          "Português"),
    "es":      Language("es",      "Spanish",             "Español"),
    "fil":     Language("fil",     "Filipino",            "Filipino"),
}


# ══════════════════════════════════════════════════════════
# 法域
# ══════════════════════════════════════════════════════════
@dataclass(frozen=True)
class Jurisdiction:
    code: JurisdictionCode
    name_en: str
    name_zh: str
    languages: list[str]           # 界面 / 输出语言
    source_languages: list[str]    # 法案【原文】语言
    data_source: str
    role: Role                     # 在系统里的角色
    prediction_ready: bool         # 数据是否已验证可做预测
    prediction_feasible: bool      # 预测任务在【制度上】是否成立
    institutional_note: str = ""   # 制度特征(决定 feasible 的原因)
    notes: str = ""


JURISDICTIONS: dict[str, Jurisdiction] = {
    "CA": Jurisdiction(
        code="CA",
        name_en="California, USA",
        name_zh="美国加利福尼亚州",
        # es / fil 是【输出翻译】语言 —— 加州无西语/菲语法案原文。
        # 目的:让西语/菲语社区看懂倡导内容并签名支持。
        languages=["en", "zh-Hans", "zh-Hant", "es", "fil"],
        source_languages=["en"],
        data_source="leginfo.legislature.ca.gov (public domain, Gov. Code 10248.5)",
        role="prediction",
        prediction_ready=True,      # 已实测:AB/SB 正负样本齐全
        prediction_feasible=True,
        institutional_note="两院制 + 党派竞争;大量法案死于委员会或被否决 → 负样本充足",
        notes="核心法域。chaptered=通过,died/vetoed=未通过,标签判定已实测验证",
    ),
    "HK": Jurisdiction(
        code="HK",
        name_en="Hong Kong SAR",
        name_zh="香港特别行政区",
        languages=["en", "zh-Hans", "zh-Hant"],
        source_languages=["en", "zh-Hant"],     # 原生中英双语
        data_source="LegCo Bills Database (open API, 1844-present)",
        role="retrieval",           # 暂定;验证后可能升为 prediction
        prediction_ready=False,     # 待 verify_hk_data.py 验证
        prediction_feasible=True,   # 制度上成立(草案确实可能撤回/失效)
        institutional_note="行政主导,政府草案通过率偏高,但仍存在撤回/失效的草案",
        notes="跑 verify_hk_data.py 验证正负样本比例:"
              "失败样本 >15% → 升为 prediction;<5% → 保持 retrieval",
    ),
    "MO": Jurisdiction(
        code="MO",
        name_en="Macau SAR",
        name_zh="澳门特别行政区",
        languages=["en", "zh-Hans", "zh-Hant", "pt"],
        source_languages=["zh-Hant", "pt"],     # 官方语言:中文 + 葡萄牙语
        data_source="Macau Legislative Assembly (no open bills API)",
        role="control",             # ★ 制度对照组
        prediction_ready=False,
        prediction_feasible=False,  # ★ 结构上不成立,非数据缺失
        institutional_note=(
            "行政主导体制。《基本法》第75条:凡涉及政府政策的议案,"
            "议员提出【之前】必须取得行政长官书面同意。"
            "→ 筛选发生在提案之前,失败的提案从未被提出 → 几乎无负样本。"
        ),
        notes="预测任务结构上不成立 —— 这不是数据缺失,是制度使然。"
              "定位:法律检索 + 制度对照组。"
              "『澳门为何无法预测』本身即是重要研究结论。",
    ),
}


# ══════════════════════════════════════════════════════════
# 显示预设 —— 改 ACTIVE_PRESET 一行即可切换
# ══════════════════════════════════════════════════════════
@dataclass(frozen=True)
class Preset:
    key: str
    label_en: str
    label_zh: str
    jurisdictions: list[JurisdictionCode]
    default_language: str
    description: str


PRESETS: dict[str, Preset] = {
    "hackathon": Preset(
        key="hackathon",
        label_en="Hackathon (HK/MO)",
        label_zh="黑客松(港澳)",
        jurisdictions=["HK", "MO"],
        default_language="zh-Hans",
        description="展示港澳法域;加州数据后台照常运行,前端不显示",
    ),
    "california": Preset(
        key="california",
        label_en="California",
        label_zh="加州显示预设",
        jurisdictions=["CA"],
        default_language="en",
        description="展示加州法域",
    ),
    "china": Preset(
        key="china",
        label_en="China",
        label_zh="中国显示预设",
        jurisdictions=["HK", "MO"],
        default_language="zh-Hans",
        description="展示港澳法域",
    ),
}

# ★★★ 改这一行就切换前端显示 ★★★
ACTIVE_PRESET: str = "hackathon"


# ══════════════════════════════════════════════════════════
# 对外接口
# ══════════════════════════════════════════════════════════
@dataclass
class ActiveConfig:
    preset: Preset
    jurisdictions: list[Jurisdiction]
    available_languages: list[Language] = field(default_factory=list)

    def to_dict(self) -> dict:
        """给前端的 JSON。"""
        return {
            "preset": {
                "key": self.preset.key,
                "label_en": self.preset.label_en,
                "label_zh": self.preset.label_zh,
            },
            "jurisdictions": [
                {
                    "code": j.code,
                    "name_en": j.name_en,
                    "name_zh": j.name_zh,
                    "role": j.role,
                    "languages": [
                        {"code": c, "native": LANGUAGES[c].name_native}
                        for c in j.languages if c in LANGUAGES
                    ],
                    "prediction_ready": j.prediction_ready,
                    "prediction_feasible": j.prediction_feasible,
                }
                for j in self.jurisdictions
            ],
            "default_language": self.preset.default_language,
        }


def get_active_config(preset: str | None = None) -> ActiveConfig:
    key = preset or ACTIVE_PRESET
    if key not in PRESETS:
        raise ValueError(f"未知预设: {key}. 可选: {list(PRESETS)}")
    p = PRESETS[key]
    js = [JURISDICTIONS[c] for c in p.jurisdictions]
    langs, seen = [], set()
    for j in js:
        for c in j.languages:
            if c not in seen and c in LANGUAGES:
                seen.add(c)
                langs.append(LANGUAGES[c])
    return ActiveConfig(preset=p, jurisdictions=js, available_languages=langs)


def is_visible(code: str, preset: str | None = None) -> bool:
    """某法域在当前预设下是否【前端显示】。后端仍会处理它。"""
    return code in get_active_config(preset).preset.jurisdictions


def all_jurisdictions() -> list[Jurisdiction]:
    """全部法域 —— 后端数据处理用这个,不受显示预设影响。"""
    return list(JURISDICTIONS.values())


def can_predict(code: str) -> bool:
    """
    该法域能不能做通过率预测?
    需同时满足:制度上成立(feasible) + 数据已验证(ready)。
    """
    j = JURISDICTIONS[code]
    return j.prediction_feasible and j.prediction_ready


def institutional_spectrum() -> list[dict]:
    """
    ★ 制度光谱 —— 按'制度约束强度'排序,用于跨法域对比研究。
    这是本项目的核心研究框架。
    """
    order = ["CA", "HK", "MO"]   # 约束由弱到强
    return [
        {
            "code": c,
            "name_zh": JURISDICTIONS[c].name_zh,
            "role": JURISDICTIONS[c].role,
            "predictable": can_predict(c),
            "feasible": JURISDICTIONS[c].prediction_feasible,
            "institutional_note": JURISDICTIONS[c].institutional_note,
        }
        for c in order
    ]
