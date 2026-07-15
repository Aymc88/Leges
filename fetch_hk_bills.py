#!/usr/bin/env python3
"""
fetch_hk_bills.py — 爬取香港立法会条例草案数据,建检索语料

数据源: LegCo Bills Database (OData API)
  https://app.legco.gov.hk/BillsDB/odata/Vbills

通过判定: 有 ordinance_gazette_date → 已通过; 否则视为未通过/待定
(注:香港验证结果显示 99.98% 通过率 → 角色为 retrieval,不做预测)
"""

from __future__ import annotations
import json, urllib.request, urllib.parse, time, argparse
from pathlib import Path

BASE = "https://app.legco.gov.hk/BillsDB/odata/Vbills"
UA = {"User-Agent": "Leges research; Hong Kong legislative corpus"}


def fetch_json(url: str) -> dict | None:
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:
        print(f"  [错误] {e}")
        return None


def fetch_all(max_records: int = 5000) -> list[dict]:
    """分页拉取全部条例草案。"""
    out = []
    skip = 0
    page = 1000
    while len(out) < max_records:
        url = f"{BASE}?$top={page}&$skip={skip}&$format=json"
        data = fetch_json(url)
        if not data:
            break
        items = data.get("value", [])
        if not items:
            break
        out.extend(items)
        print(f"  已拉取 {len(out)} 条…")
        if len(items) < page:
            break
        skip += page
    return out


def judge_passed(bill: dict) -> bool | None:
    """判定一条草案是否通过。有 ordinance_gazette_date = 通过。"""
    if bill.get("ordinance_gazette_date"):
        return True
    # 检查是否有 Withdrawn / Lapsed 标志
    title = (bill.get("bill_title_eng") or "") + (bill.get("bill_title_chi") or "")
    if "withdraw" in title.lower() or "lapse" in title.lower():
        return False
    return None


def transform(record: dict) -> dict:
    """将 OData 记录转为统一格式。"""
    title_en = (record.get("bill_title_eng") or "").strip()
    title_zh = (record.get("bill_title_chi") or "").strip()
    title = title_en or title_zh

    passed = judge_passed(record)

    return {
        "bill_id": f"HK-{record.get('internal_key', '')}",
        "jurisdiction": "HK",
        "title": title[:200],
        "title_en": title_en,
        "title_zh": title_zh,
        "ordinance_title_eng": (record.get("ordinance_title_eng") or "").strip(),
        "ordinance_title_chi": (record.get("ordinance_title_chi") or "").strip(),
        "proposed_by_eng": (record.get("proposed_by_eng") or "").strip(),
        "proposed_by_chi": (record.get("proposed_by_chi") or "").strip(),
        "bill_gazette_date": record.get("bill_gazette_date", ""),
        "first_reading_date": record.get("first_reading_date", ""),
        "second_reading_date": record.get("second_reading_date", ""),
        "third_reading_date": record.get("third_reading_date", ""),
        "ordinance_gazette_date": record.get("ordinance_gazette_date", ""),
        "passed": passed,
        "status": "Passed" if passed else ("Failed/Withdrawn" if passed is False else "Unknown"),
        "role": "retrieval",
        "url_en": record.get("bill_content_url_eng", ""),
        "url_zh": record.get("bill_content_url_chi", ""),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=5000, help="最大拉取条数")
    ap.add_argument("--out", default="output/hk_bills.jsonl")
    args = ap.parse_args()

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("香港立法会条例草案数据拉取")
    print("=" * 60)

    bills = fetch_all(max_records=args.max)
    print(f"\n共 {len(bills)} 条原始记录")

    records = [transform(b) for b in bills]

    n_pass = sum(1 for r in records if r["passed"] is True)
    n_fail = sum(1 for r in records if r["passed"] is False)
    n_unk = sum(1 for r in records if r["passed"] is None)

    print(f"\n结果:")
    print(f"  通过:     {n_pass}")
    print(f"  未通过:   {n_fail}")
    print(f"  无法判定: {n_unk}")
    print(f"\n  (香港角色: retrieval — 仅用于检索/对比,不做预测)")

    with open(args.out, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\n  输出: {args.out}")


if __name__ == "__main__":
    main()
