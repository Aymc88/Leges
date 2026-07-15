#!/usr/bin/env python3
"""
fetch_mo_laws.py — 爬取澳门立法会法案,建检索语料 + 统计通过率证据

★ 澳门在 Leges 里的角色:制度对照组(control),不做通过率预测。
   原因(《基本法》第75条):凡涉及政府政策的议案,议员提出【之前】
   必须取得行政长官书面同意 → 筛选发生在提案之前 → 几乎无失败样本。

   本脚本的两个目的:
     ① 建检索语料(澳门法案可被搜索、可与加州/香港对比)
     ② 【实证】统计"未通过"法案占比 —— 用真实数字证明制度光谱,
        而不是空口断言。这是可写进论文的制度光谱实证。

数据源(公开网页,非 API):
    https://www.al.gov.mo/zh/law/lawcase/{id}     法案详情页
    https://www.al.gov.mo/pt/law/lawcase/{id}     葡文版
    页面含:法案名、最初文本、修改文本、委员会意见书、
           一般性讨论及表决日期、细则性讨论及表决日期

通过判定(基于澳门立法流程):
    澳门法案须过两关 —— 一般性表决 + 细则性表决。
      有【细则性讨论及表决】日期  → passed = 1(走完流程)
      仅有【一般性表决】无细则性  → passed = 0(卡住/未完成)
      两者皆无                    → passed = None(可能刚提交)

用法:
    python fetch_mo_laws.py --start 1 --end 400
    python fetch_mo_laws.py --start 300 --end 350   # 小范围试跑

输出:
    output/mo_laws.jsonl   结构化法案数据
    终端打印:通过/未通过统计 —— 这就是制度光谱的实证
"""

from __future__ import annotations
import re
import json
import time
import argparse
import urllib.request
import urllib.error
from pathlib import Path
from html import unescape

BASE = "https://www.al.gov.mo/zh/law/lawcase"
UA = {"User-Agent": "Mozilla/5.0 (Leges academic research; legislative corpus)"}

# 礼貌限速 —— 别把人家网站爬挂了
DELAY_SEC = 1.5


def fetch(url: str) -> str | None:
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        print(f"  [HTTP {e.code}] {url}")
        return None
    except Exception as e:
        print(f"  [错误] {url}: {e}")
        return None


def strip_tags(html: str) -> str:
    html = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<style.*?</style>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", unescape(html)).strip()


def parse_law(html: str, law_id: int) -> dict | None:
    """
    从法案详情页抽取结构化信息。
    页面真实结构(已核实 lawcase/341《仲裁法》):
        法案 - 仲裁法
        法案最初文本  - 2018-05-24
        法案修改文本 - 2019-07-30
        一般性討論及表決 - 2018-06-07
        細則性討論及表決 - 2019-10-17
    """
    text = strip_tags(html)

    # ── 法案名称:「法案 - XXX」
    m = re.search(r"法案\s*[-–—]\s*([^\s|]{2,60}?)(?:\s{2,}|理由陳述|$)", text)
    title = m.group(1).strip() if m else ""
    if not title:
        # 兜底:找 <title> 之外的第一个"法案 - "
        m2 = re.search(r"法案\s*[-–—]\s*(\S+)", text)
        title = m2.group(1).strip() if m2 else ""
    if not title:
        return None   # 不是法案页

    def find_date(label_pattern: str) -> str | None:
        m = re.search(label_pattern + r"[^\d]{0,20}(\d{4}-\d{2}-\d{2})", text)
        return m.group(1) if m else None

    initial_date  = find_date(r"法案最初文本")
    revised_date  = find_date(r"法案修改文本")
    general_vote  = find_date(r"一般性討論及表決")   # 第一关
    detail_vote   = find_date(r"細則性討論及表決")   # 第二关(过了=通过)

    # ── 通过判定 ──
    if detail_vote:
        passed, status = 1, "細則性表決通過"
    elif general_vote:
        passed, status = 0, "僅一般性表決,未完成細則性"
    else:
        passed, status = None, "無表決記錄(可能剛提交)"

    # 委员会意见书
    committee = bool(re.search(r"常設委員會", text))

    # PDF 链接
    pdfs = re.findall(r"https://www\.al\.gov\.mo/uploads/attachment/[^\s\)\"']+\.pdf", html)

    return {
        "law_id": law_id,
        "jurisdiction": "MO",
        "title": title,
        "url_zh": f"{BASE}/{law_id}",
        "url_pt": f"https://www.al.gov.mo/pt/law/lawcase/{law_id}",
        "initial_text_date": initial_date,
        "revised_text_date": revised_date,
        "general_vote_date": general_vote,
        "detail_vote_date": detail_vote,
        "has_committee_opinion": committee,
        "passed": passed,
        "status": status,
        "pdf_links": pdfs[:10],
        # ★ 提醒:澳门不做预测,此 passed 字段仅用于统计制度光谱的实证
        "role": "control",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--end", type=int, default=400)
    ap.add_argument("--out", default="output/mo_laws.jsonl")
    ap.add_argument("--delay", type=float, default=DELAY_SEC)
    args = ap.parse_args()

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)

    print("=" * 64)
    print("澳门立法会法案爬取")
    print("目的:① 建检索语料  ② 实证'制度光谱'(统计未通过占比)")
    print("=" * 64)
    print(f"范围: lawcase/{args.start} … {args.end}   限速 {args.delay}s\n")

    records = []
    miss = 0
    for i in range(args.start, args.end + 1):
        html = fetch(f"{BASE}/{i}")
        if html is None:
            miss += 1
            if miss > 30:      # 连续大量 404,认为到头了
                print(f"  连续 {miss} 个不存在,停止。")
                break
            continue
        rec = parse_law(html, i)
        if rec:
            miss = 0
            records.append(rec)
            flag = {1: "✅通过", 0: "⏸未完成", None: "…无记录"}[rec["passed"]]
            print(f"  [{i:>4}] {flag}  {rec['title'][:30]}")
        time.sleep(args.delay)

    # ── 写出 ──
    with open(args.out, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # ── ★ 实证统计:这就是制度光谱的证据 ──
    n = len(records)
    n_pass = sum(1 for r in records if r["passed"] == 1)
    n_fail = sum(1 for r in records if r["passed"] == 0)
    n_none = sum(1 for r in records if r["passed"] is None)
    known = n_pass + n_fail

    print("\n" + "=" * 64)
    print("★ 实证结果 —— 澳门法案通过情况")
    print("=" * 64)
    print(f"  抓到法案      {n}")
    print(f"  细则性表决通过 {n_pass}")
    print(f"  未完成细则性   {n_fail}")
    print(f"  无表决记录     {n_none}")
    if known:
        fail_ratio = n_fail / known
        print(f"\n  【未通过占比】 {fail_ratio*100:.1f}%  ({n_fail}/{known})")
        print()
        if fail_ratio < 0.05:
            print("  ✅ 证实了制度光谱的假设:")
            print("     澳门未通过样本 <5% —— 负样本几乎不存在,")
            print("     通过率预测任务【结构上不成立】。")
            print()
            print("     根因(《基本法》第75条):涉及政府政策的议案,")
            print("     议员提出【之前】须获行政长官书面同意")
            print("     → 筛选发生在提案之前,失败的提案从未被提出。")
            print()
            print("  📄 这组数字可直接写进论文,作为制度光谱的实证。")
        else:
            print(f"  ⚠️ 未通过占比 {fail_ratio*100:.1f}%,高于预期。")
            print("     需重新检视判定逻辑,或澳门比预想的更有可预测性。")
    print(f"\n  输出: {args.out}")
    print("\n  ※ 澳门角色仍为 control(对照组)—— 本 passed 字段")
    print("    仅用于统计制度光谱,不用于训练预测模型。")


if __name__ == "__main__":
    main()
