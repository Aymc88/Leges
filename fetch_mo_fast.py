#!/usr/bin/env python3
"""Fast concurrent fetcher for Macau legislative data."""
import urllib.request, json, re
from html import unescape
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = "https://www.al.gov.mo/zh/law/lawcase"
UA = {"User-Agent": "Leges academic research"}

def fetch(i):
    req = urllib.request.Request(f"{BASE}/{i}", headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return i, r.read().decode("utf-8", "replace")
    except:
        return i, None

def strip_html(html):
    html = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<style.*?</style>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", unescape(html)).strip()

def find_date(text, label):
    m = re.search(label + r"[^\d]{0,20}(\d{4}-\d{2}-\d{2})", text)
    return m.group(1) if m else None

results = []
print("Fetching MO laws 1-400 (concurrent, 10s timeout)...")
with ThreadPoolExecutor(max_workers=8) as pool:
    fs = {pool.submit(fetch, i): i for i in range(1, 401)}
    for f in as_completed(fs):
        i, html = f.result()
        if html is None:
            continue
        text = strip_html(html)
        m = re.search(r"法案\s*[-–—]\s*([^\s|]{2,60}?)", text)
        if not m:
            continue
        title = m.group(1).strip()
        if not title or len(title) < 2:
            continue

        rec = {
            "law_id": i,
            "jurisdiction": "MO",
            "title": title,
            "url_zh": f"{BASE}/{i}",
            "url_pt": f"https://www.al.gov.mo/pt/law/lawcase/{i}",
            "initial_text_date": find_date(text, "法案最初文本"),
            "revised_text_date": find_date(text, "法案修改文本"),
            "general_vote_date": find_date(text, "一般性討論及表決"),
            "detail_vote_date": find_date(text, "細則性討論及表決"),
            "passed": None,
            "status": "無表決記錄",
            "role": "control",
        }
        dv = rec["detail_vote_date"]
        gv = rec["general_vote_date"]
        if dv:
            rec["passed"] = 1
            rec["status"] = "細則性表決通過"
        elif gv:
            rec["passed"] = 0
            rec["status"] = "僅一般性表決，未完成細則性"

        results.append(rec)
        flag = {1: "PASS", 0: "FAIL", None: "NONE"}[rec["passed"]]
        print(f"  [{i:>4}] {flag}  {title[:30]}")

results.sort(key=lambda r: r["law_id"])
with open("output/mo_laws.jsonl", "w", encoding="utf-8") as f:
    for r in results:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

n = len(results)
n_pass = sum(1 for r in results if r["passed"] == 1)
n_fail = sum(1 for r in results if r["passed"] == 0)
n_none = sum(1 for r in results if r["passed"] is None)
known = n_pass + n_fail

print("\n" + "=" * 60)
print("Macau Legislative Data - Results")
print("=" * 60)
print(f"  Laws found:  {n}")
print(f"  Passed:      {n_pass}")
print(f"  Failed:      {n_fail}")
print(f"  No record:   {n_none}")
if known:
    fail_ratio = n_fail / known
    print(f"\n  Fail ratio:  {fail_ratio*100:.1f}%  ({n_fail}/{known})")
    if fail_ratio < 0.05:
        print("\n  CONFIRMED: Institutional spectrum hypothesis validated!")
    else:
        print(f"\n  NOTE: Fail ratio {fail_ratio*100:.1f}%, higher than expected")
print(f"\n  Output: output/mo_laws.jsonl")
