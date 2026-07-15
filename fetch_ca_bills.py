#!/usr/bin/env python3
"""
fetch_ca_bills.py — 爬取加州 AB/SB 法案数据,建预测语料

数据源: California Legislative Information (leginfo.legislature.ca.gov)
  法案状态页: billStatusClient.xhtml?bill_id={bill_id}

通过判定:
  Chaptered / Chapter / Approved → passed (1)
  Died / Vetoed → failed (0)
  其他(Active, Pending, etc.) → None (待定)

用法:
    python fetch_ca_bills.py --year 2025 --max 100
    python fetch_ca_bills.py --year 2025 --house Assembly --max 50   # 仅众议院
"""

from __future__ import annotations
import re, json, time, argparse, sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from html import unescape

UA = {"User-Agent": "Leges research; California legislative corpus builder"}
BASE = "https://leginfo.legislature.ca.gov/faces"
DELAY = 0.3  # 礼貌限速


def fetch(url: str, timeout: int = 15) -> str | None:
    req = Request(url, headers=UA)
    try:
        with urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except (HTTPError, URLError, OSError) as e:
        return None


def build_bill_id(year: int, house: str, num: int) -> str:
    """Build leginfo bill_id, e.g. 202520260AB1"""
    yy = year % 100
    next_yy = (year + 1) % 100 if (year + 1) % 100 != 0 else 100
    session = f"{year}{year+1}"
    return f"{session}0{house}{num}"


def bill_type(code: str) -> str:
    return {"AB": "Assembly Bill", "SB": "Senate Bill"}.get(code, code)


def parse_status(html: str) -> dict | None:
    """从法案状态页提取结构化信息。"""
    if not html:
        return None

    text = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", unescape(text)).strip()

    # ── 法案标题:通常在 <title> 附近 —— "AB-1 Residential property..."
    title = ""
    m = re.search(r"(?:AB|SB)\s*-\s*\d+\s+(.+?)(?:\s{2,}|$)", text)
    if m:
        title = m.group(1).strip()
    # 兜底:找 title meta
    if not title:
        m2 = re.search(r"AB\s*\d+\s*[–-]\s*(.+?)(?:\s{2,}|$)", text)
        if m2:
            title = m2.group(1).strip()

    # ── 通过判定 ──
    # 找状态关键词
    status_text = text[:2000]  # 只看页面前面部分
    # 找 Chapter/Chaptered
    if re.search(r"\bChaptered\b", status_text, re.I):
        passed, status = 1, "Chaptered"
    elif re.search(r"\bChapter\s+\d+\b", status_text):
        passed, status = 1, "Chaptered"
    elif re.search(r"\bApproved\b", status_text) and re.search(r"Governor", status_text):
        passed, status = 1, "Approved by Governor"
    elif re.search(r"\bVetoed\b", status_text, re.I):
        passed, status = 0, "Vetoed"
    elif re.search(r"\bDied\b", status_text, re.I):
        passed, status = 0, "Died"
    elif re.search(r"\bFailed\b", status_text, re.I):
        passed, status = 0, "Failed"
    else:
        passed, status = None, "Unknown/Active"

    # ── 描述:从 meta description 获取
    desc = ""
    md = re.search(r'<meta\s+name="description"\s+content="([^"]+)"', html)
    if md:
        desc = md.group(1).strip()

    # ── 法案主题分类 —— 从法案标题推测
    subject = classify_subject(title + " " + desc)

    return {
        "title": title or desc,
        "description": desc,
        "passed": passed,
        "status": status,
        "subject": subject,
    }


def classify_subject(text: str) -> str:
    """简单对法案进行分类。"""
    text_lower = text.lower()
    categories = {
        "housing": ["housing", "rental", "homeless", "property", "tenants", "eviction", "landlord",
                     "zoning", "shelter", "mortgage", "foreclosure", "real estate"],
        "environment": ["climate", "environment", "energy", "renewable", "emission", "pollution",
                        "wildfire", "fire", "water", "air", "clean energy", "solar", "green"],
        "education": ["education", "school", "student", "teacher", "college", "university",
                      "curriculum", "tuition", "k-12", "community college"],
        "healthcare": ["health", "medical", "hospital", "medicaid", "medicare", "insurance",
                       "patient", "doctor", "nurse", "mental health", "public health"],
        "criminal justice": ["criminal", "prison", "police", "sentence", "crime", "offense",
                              "inmate", "parole", "probation", "felony", "misdemeanor"],
        "transportation": ["transportation", "road", "highway", "bridge", "transit", "traffic",
                           "dmv", "vehicle", "driver", "license", "rail", "caltrans"],
        "tax & budget": ["tax", "budget", "revenue", "finance", "fund", "appropriation",
                         "fiscal", "bond", "expenditure", "levy"],
        "labor & employment": ["labor", "employment", "wage", "worker", "employee", "employer",
                               "union", "unemployment", "minimum wage", "benefit", "pension"],
        "technology": ["technology", "data", "privacy", "ai", "artificial intelligence",
                       "cybersecurity", "internet", "digital", "broadband", "software"],
    }
    for cat, keywords in categories.items():
        if any(kw in text_lower for kw in keywords):
            return cat
    return "other"


def fetch_bill_list(year: int, house: str, start: int, end: int) -> list[int]:
    """
    通过顺序探测获取有效法案编号列表。
    leginfo 的搜索需要 POST,所以我们逐一探测 bill_id。
    跳过空/404 页面。
    """
    found = []
    for num in range(start, end + 1):
        bid = build_bill_id(year, house, num)
        url = f"{BASE}/billStatusClient.xhtml?bill_id={bid}"
        html = fetch(url)
        if html and "Bill Status" in html and len(html) > 1000:
            found.append(num)
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2025)
    ap.add_argument("--house", choices=["Assembly", "Senate"], default="Assembly")
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--end", type=int, default=100)
    ap.add_argument("--out", default="output/ca_bills.jsonl")
    ap.add_argument("--delay", type=float, default=DELAY)
    args = ap.parse_args()

    code = "AB" if args.house == "Assembly" else "SB"
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)

    print("=" * 64)
    print(f"加州 {code} 法案数据爬取 ({args.year}-{args.year+1} 会期)")
    print(f"范围: {code} {args.start}–{args.end}")
    print("=" * 64)

    bills = []
    for num in range(args.start, args.end + 1):
        bid = build_bill_id(args.year, code, num)
        url = f"{BASE}/billStatusClient.xhtml?bill_id={bid}"
        html = fetch(url, timeout=10)
        if not html or len(html) < 500:
            continue

        info = parse_status(html)
        if not info or not info["title"]:
            continue

        record = {
            "bill_id": f"{code}{num}",
            "session": f"{args.year}-{args.year+1}",
            "house": args.house,
            "jurisdiction": "CA",
            "url": f"https://leginfo.legislature.ca.gov/faces/billStatusClient.xhtml?bill_id={bid}",
            **info,
        }
        bills.append(record)
        flag = {1: "✅通過", 0: "❌失敗", None: "⋯待定"}[record["passed"]]
        subj = record["subject"][:12]
        print(f"  [{code}{num:>4}] {flag} {record['status']:12s} | {subj:12s} | {record['title'][:40]}")

        time.sleep(args.delay)

    # 写出
    with open(args.out, "w", encoding="utf-8") as f:
        for b in bills:
            f.write(json.dumps(b, ensure_ascii=False) + "\n")

    # 统计
    n = len(bills)
    n_pass = sum(1 for b in bills if b["passed"] == 1)
    n_fail = sum(1 for b in bills if b["passed"] == 0)
    n_unk = sum(1 for b in bills if b["passed"] is None)

    print("\n" + "=" * 64)
    print("★ 加州法案数据统计")
    print("=" * 64)
    print(f"  总法案:     {n}")
    print(f"  通过(章):   {n_pass}")
    print(f"  失败:       {n_fail}")
    print(f"  待定:       {n_unk}")
    if n_pass + n_fail > 0:
        print(f"  失败占比:   {n_fail/(n_pass+n_fail)*100:.1f}%")
    if n > 0:
        subject_dist = {}
        for b in bills:
            s = b["subject"]
            subject_dist[s] = subject_dist.get(s, 0) + 1
        print(f"\n  主题分布:")
        for s, c in sorted(subject_dist.items(), key=lambda x: -x[1]):
            print(f"    {s:20s}: {c}")
    print(f"\n  输出: {args.out}")


if __name__ == "__main__":
    main()
