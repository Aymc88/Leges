#!/usr/bin/env python3
"""
verify_hk_data.py — 验证香港立法会条例草案数据是否支持"通过率预测"

★ 这是 v2 架构的关键验证。先跑这个,再决定香港做预测还是只做检索。

要验证的致命问题:
    香港条例草案多由政府提出,政府草案通过率极高。
    若数据里 95%+ 都是"通过",分类任务退化 ——
    模型永远猜"通过"就有 95% 准确率,毫无价值。

数据源:
    香港立法会 Bills Database(开放数据,有 API)
    https://www.legco.gov.hk/en/open-legco/open-data/bills-database.html

判定标准(通过 = 三读通过并刊宪成为条例):
    看条例草案的关键日期字段 —— 有"通过日期/生效日期" = 通过
    无、或标记为撤回/失效 = 未通过

用法:
    python verify_hk_data.py

输出:
    正负样本比例 + 明确的架构建议(做预测 or 只做检索)
"""

from __future__ import annotations
import json
import urllib.request
import urllib.parse
from collections import Counter

# 香港立法会 Bills Database 的 OData 端点
# 注:实际端点需按官方 API 文档核实,这里是通用查询模式
BASE = "https://app.legco.gov.hk/BillsDB/odata/Vbills"

UA = {"User-Agent": "Mozilla/5.0 (Leges research; bill passage study)"}


def fetch(url: str) -> dict:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def probe_schema():
    """先拉几条,看看字段长什么样 —— 不猜,先看。"""
    url = f"{BASE}?$top=3&$format=json"
    print(f">> 探测 schema: {url}\n")
    try:
        data = fetch(url)
    except Exception as e:
        print(f"❌ 拉取失败: {e}")
        print("   可能原因:端点变了 / 需要不同的查询格式。")
        print("   请到官方文档核实端点:")
        print("   https://www.legco.gov.hk/en/open-legco/open-data/bills-database.html")
        return None

    items = data.get("value", data if isinstance(data, list) else [])
    if not items:
        print("⚠️ 返回空,检查端点。")
        return None

    print("字段清单(第一条):")
    for k, v in items[0].items():
        preview = str(v)[:60] if v is not None else "None"
        print(f"  {k:35} = {preview}")
    print()
    return items


def fetch_all(max_records: int = 5000) -> list[dict]:
    """分页拉取全部条例草案。"""
    out = []
    skip = 0
    page = 1000
    while len(out) < max_records:
        url = f"{BASE}?$top={page}&$skip={skip}&$format=json"
        try:
            data = fetch(url)
        except Exception as e:
            print(f"  [警告] 第 {skip} 条起拉取失败: {e}")
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
    """
    判定一条草案是否通过。
    策略:找任何表示"通过/生效/刊宪"的日期字段 —— 有值 = 通过。
    找不到明确字段时返回 None(需人工核对字段名)。
    """
    keys = {k.lower(): k for k in bill.keys()}
    # 可能表示"通过"的字段名候选
    pass_hints = [
        "ordinance", "passed", "enact", "commencement", "gazett",
        "thirdreading", "third_reading",
    ]
    # 可能表示"未通过"的
    fail_hints = ["withdraw", "lapse", "negatived", "rejected"]

    for lk, orig in keys.items():
        if any(h in lk for h in fail_hints) and bill[orig]:
            return False
    for lk, orig in keys.items():
        if any(h in lk for h in pass_hints) and bill[orig]:
            return True
    return None


def main():
    print("=" * 60)
    print("香港立法会条例草案数据验证")
    print("目的:确认是否有足够的【未通过】样本支撑预测任务")
    print("=" * 60 + "\n")

    items = probe_schema()
    if items is None:
        return

    print(">> 拉取全部数据…")
    bills = fetch_all()
    print(f"   共 {len(bills)} 条\n")

    if not bills:
        print("❌ 没拿到数据,无法验证。")
        return

    results = Counter()
    for b in bills:
        r = judge_passed(b)
        results["通过" if r is True else "未通过" if r is False else "无法判定"] += 1

    total = sum(results.values())
    n_pass = results["通过"]
    n_fail = results["未通过"]
    n_unk = results["无法判定"]

    print("=" * 60)
    print("结果")
    print("=" * 60)
    print(f"  总计      {total}")
    print(f"  通过      {n_pass}  ({n_pass/total*100:.1f}%)")
    print(f"  未通过    {n_fail}  ({n_fail/total*100:.1f}%)")
    print(f"  无法判定  {n_unk}  ({n_unk/total*100:.1f}%)")
    print()

    # ── 架构建议 ──
    print("=" * 60)
    print("架构建议")
    print("=" * 60)

    if n_unk > total * 0.5:
        print("⚠️ 超过一半无法判定 —— 字段名没对上。")
        print("   看上面打印的字段清单,手动确认哪个字段表示'通过',")
        print("   再改 judge_passed() 里的 pass_hints / fail_hints。")
        return

    known = n_pass + n_fail
    if known == 0:
        print("❌ 没有可判定的样本。")
        return

    fail_ratio = n_fail / known
    print(f"  未通过样本占比: {fail_ratio*100:.1f}%\n")

    if fail_ratio < 0.05:
        print("❌ 【香港不适合做预测】")
        print("   未通过样本 <5%,分类任务退化 ——")
        print("   模型永远猜'通过'就有 95%+ 准确率,毫无价值。")
        print()
        print("   ✅ 建议改为:香港只做【检索 / 对比】,不做预测。")
        print("   ✅ 并把'香港草案近乎全通过'写成研究发现 —— 这本身有价值,")
        print("      可作为研究发现(不同法域立法通过机制的差异)。")
    elif fail_ratio < 0.15:
        print("⚠️ 【勉强可做,但要小心】")
        print(f"   未通过仅 {fail_ratio*100:.1f}%,类别严重不平衡。")
        print("   若要做预测,必须:")
        print("     - 用 AUC / F1 评估,不能只看准确率")
        print("     - 做类别平衡处理")
        print("     - 诚实报告基线(全猜通过的准确率是多少)")
    else:
        print("✅ 【香港可以做预测】")
        print(f"   未通过样本 {fail_ratio*100:.1f}%,正负样本比例健康。")
        print("   可以和加州并列做跨法域预测,这是项目的强亮点。")


if __name__ == "__main__":
    main()
