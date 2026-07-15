#!/usr/bin/env python3
"""
search_tool.py — 跨法域法案语义搜索工具

使用 ChromaDB 向量库进行语义搜索,支持按法域、状态等过滤。

用法:
    python search_tool.py --query "wildfire insurance"
    python search_tool.py --query "housing" --jurisdiction CA
    python search_tool.py --query "人工智能" --jurisdiction MO
    python search_tool.py --query "passed bills" --status passed
"""

from __future__ import annotations
import argparse, sys
from pathlib import Path
from sentence_transformers import SentenceTransformer
import chromadb
from chromadb.config import Settings


DB_PATH = "data/vector_store"
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def search(
    query: str,
    jurisdiction: str | None = None,
    status: str | None = None,
    n_results: int = 10,
) -> list[dict]:
    """执行语义搜索。"""

    # 选择 collection
    jur_collections = {"CA": "ca_bills", "MO": "mo_laws", "HK": "hk_bills"}
    if jurisdiction and jurisdiction in jur_collections:
        collection_name = jur_collections[jurisdiction]
    else:
        collection_name = None  # 全部搜索

    db = chromadb.PersistentClient(
        path=DB_PATH,
        settings=Settings(anonymized_telemetry=False),
    )

    model = SentenceTransformer(MODEL_NAME)
    query_emb = model.encode([query])[0].tolist()

    results = []
    if collection_name:
        cols = [collection_name]
    else:
        cols = [c.name for c in db.list_collections() if c.name in jur_collections.values()]

    for col_name in cols:
        col = db.get_collection(col_name)

        # 构建过滤条件
        where = {}
        if jurisdiction:
            where["jurisdiction"] = jurisdiction
        if status:
            where["status"] = status

        try:
            res = col.query(
                query_embeddings=[query_emb],
                n_results=n_results,
                where=where if where else None,
            )
        except Exception:
            # 如果过滤条件不匹配,回退到无过滤
            res = col.query(
                query_embeddings=[query_emb],
                n_results=n_results,
            )

        if res and res["ids"]:
            for i in range(len(res["ids"][0])):
                results.append({
                    "id": res["ids"][0][i],
                    "score": float(res["distances"][0][i]) if res.get("distances") else 0,
                    "document": res["documents"][0][i] if res.get("documents") else "",
                    "metadata": res["metadatas"][0][i] if res.get("metadatas") else {},
                })

    # 按距离排序(越小越相似)
    results.sort(key=lambda r: r["score"])
    return results[:n_results]


def format_results(results: list[dict]) -> str:
    lines = []
    for i, r in enumerate(results, 1):
        meta = r["metadata"]
        score = 1 - min(r["score"] / 2, 1)  # 转为相似度百分比
        lines.append(f"  [{i}] {meta.get('bill_id', meta.get('jurisdiction','?'))}  "
                     f"(相似度: {score:.0%})")
        lines.append(f"       法域: {meta.get('jurisdiction','')}  |  "
                     f"状态: {meta.get('status','')}  |  "
                     f"主题: {meta.get('subject','')}")
        lines.append(f"       标题: {meta.get('title','')}")
        lines.append(f"       内容: {r['document'][:120]}...")
        lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Leges 跨法域法案语义搜索")
    ap.add_argument("--query", "-q", required=True, help="搜索关键词")
    ap.add_argument("--jurisdiction", "-j", choices=["CA", "HK", "MO"], help="法域过滤")
    ap.add_argument("--status", "-s", help="状态过滤(如 Chaptered/Died)")
    ap.add_argument("--top-k", "-k", type=int, default=10, help="返回条数")
    args = ap.parse_args()

    print("=" * 60)
    print(f"🔍 搜索: \"{args.query}\"")
    if args.jurisdiction:
        print(f"   法域: {args.jurisdiction}")
    print("=" * 60)

    results = search(
        query=args.query,
        jurisdiction=args.jurisdiction,
        status=args.status,
        n_results=args.top_k,
    )

    if not results:
        print("  没有找到结果。")
        return

    print(format_results(results))
    print(f"共找到 {len(results)} 条结果")


if __name__ == "__main__":
    main()
