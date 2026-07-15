#!/usr/bin/env python3
"""
build_vector_store.py — 构建 ChromaDB 向量库,用于跨法域法案语义搜索

输入:
    output/ca_bills.jsonl      加州法案数据
    output/mo_laws.jsonl       澳门法案数据 (可选)
    output/hk_bills.jsonl      香港法案数据 (可选)

输出:
    data/vector_store/          ChromaDB 持久化目录

每一条法案被切分为:
    - 法案元数据 (标题/描述/状态/法域)
    - bill text embedding (使用 Sentence-Transformers)
"""

from __future__ import annotations
import json, argparse, sys
from pathlib import Path

# === 使用 CPU 上的 Sentence-Transformers 生成嵌入 ===
from sentence_transformers import SentenceTransformer
import chromadb
from chromadb.config import Settings
from chromadb.errors import NotFoundError


# 嵌入模型 —— 多语言支持好,适合 CA/HK/MO 跨法域
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
# 替代选项(如果有多语言需求):
# "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

CHUNK_SIZE = 350  # 每块字符数(约 50-80 tokens)


def load_jsonl(path: str) -> list[dict]:
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def make_bill_text(record: dict) -> str:
    """将法案记录转为可用于搜索/嵌入的文本。"""
    parts = [
        f"Bill: {record.get('bill_id', '')}",
        f"Jurisdiction: {record.get('jurisdiction', '')}",
        f"Title: {record.get('title', '')}",
        f"Description: {record.get('description', '')}",
        f"Status: {record.get('status', '')}",
        f"Subject: {record.get('subject', '')}",
    ]
    # 澳门数据字段不同
    if "law_id" in record:
        parts = [
            f"Bill: MO Law {record.get('law_id', '')}",
            f"Jurisdiction: MO",
            f"Title: {record.get('title', '')}",
            f"Status: {record.get('status', '')}",
        ]
    # 香港数据字段不同
    if record.get("jurisdiction") == "HK":
        parts = [
            f"Bill: {record.get('bill_id', '')}",
            f"Jurisdiction: HK",
            f"Title: {record.get('title', '')}",
            f"Title EN: {record.get('title_en', '')}",
            f"Title ZH: {record.get('title_zh', '')}",
            f"Ordinance: {record.get('ordinance_title_eng', '')}",
            f"Proposed by: {record.get('proposed_by_eng', '')}",
            f"Status: {record.get('status', '')}",
            f"Passed: {record.get('passed', '')}",
        ]
    return "\n".join(p for p in parts if p)


def chunk_text(text: str, bill_id: str, chunk_size: int = CHUNK_SIZE) -> list[tuple[str, int]]:
    """将文本切块,返回 (chunk_text, chunk_index) 列表。"""
    if len(text) <= chunk_size:
        return [(text, 0)]
    chunks = []
    for i in range(0, len(text), chunk_size):
        chunk = text[i:i + chunk_size]
        chunks.append((chunk, i // chunk_size))
    return chunks


def build_collection(
    records: list[dict],
    collection_name: str,
    model: SentenceTransformer,
    db: chromadb.PersistentClient,
) -> int:
    """为一个法域的数据构建 ChromaDB collection。"""
    try:
        db.delete_collection(collection_name)
    except (ValueError, NotFoundError):
        pass  # 不存在

    collection = db.create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )

    bill_ids, texts, metadatas = [], [], []
    for record in records:
        bill_text = make_bill_text(record)
        chunks = chunk_text(bill_text, record.get("bill_id", record.get("law_id", "?")))
        for chunk_text_content, chunk_idx in chunks:
            doc_id = f"{record.get('bill_id', record.get('law_id', '?'))}_ch{chunk_idx}"
            bill_ids.append(doc_id)
            texts.append(chunk_text_content)
            metadatas.append({
                "bill_id": str(record.get("bill_id", record.get("law_id", ""))),
                "jurisdiction": record.get("jurisdiction", ""),
                "title": record.get("title", "")[:100],
                "status": record.get("status", ""),
                "passed": str(record.get("passed", "")),
                "subject": record.get("subject", ""),
                "chunk_index": chunk_idx,
            })

    if not texts:
        return 0

    # 批量生成嵌入
    embeddings = model.encode(texts, show_progress_bar=True).tolist()

    # 写入 ChromaDB
    collection.add(
        ids=bill_ids,
        documents=texts,
        embeddings=embeddings,
        metadatas=metadatas,
    )
    return len(texts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ca", default="output/ca_bills.jsonl", help="加州法案数据")
    ap.add_argument("--mo", default="output/mo_laws.jsonl", help="澳门法案数据")
    ap.add_argument("--hk", default="", help="香港法案数据(可选)")
    ap.add_argument("--db", default="data/vector_store", help="ChromaDB 持久化路径")
    ap.add_argument("--model", default=EMBED_MODEL, help="Sentence-Transformers 模型")
    args = ap.parse_args()

    db_path = Path(args.db)
    db_path.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Leges 跨法域向量库构建")
    print("=" * 60)

    # 加载模型
    print(f"\n>> 加载嵌入模型: {args.model}")
    model = SentenceTransformer(args.model)
    print(f"   模型维度: {model.get_sentence_embedding_dimension()}")

    # 连接 ChromaDB
    db = chromadb.PersistentClient(
        path=str(db_path),
        settings=Settings(anonymized_telemetry=False),
    )

    total_chunks = 0

    # ── 加州 ──
    ca_path = Path(args.ca)
    if ca_path.exists():
        print(f"\n>> 加载加州数据: {ca_path}")
        ca_records = load_jsonl(str(ca_path))
        print(f"   共 {len(ca_records)} 条法案")
        n = build_collection(ca_records, "ca_bills", model, db)
        total_chunks += n
        print(f"   ✅ 写入 {n} 个向量块 → collection 'ca_bills'")
    else:
        print(f"\n⚠️  未找到加州数据: {ca_path}")

    # ── 澳门 ──
    mo_path = Path(args.mo)
    if mo_path.exists():
        print(f"\n>> 加载澳门数据: {mo_path}")
        mo_records = load_jsonl(str(mo_path))
        print(f"   共 {len(mo_records)} 条法案")
        n = build_collection(mo_records, "mo_laws", model, db)
        total_chunks += n
        print(f"   ✅ 写入 {n} 个向量块 → collection 'mo_laws'")
    else:
        print(f"\n⚠️  未找到澳门数据: {mo_path}")

    # ── 香港 ──
    hk_path = Path(args.hk) if args.hk else None
    if hk_path and hk_path.exists():
        print(f"\n>> 加载香港数据: {hk_path}")
        hk_records = load_jsonl(str(hk_path))
        print(f"   共 {len(hk_records)} 条法案")
        n = build_collection(hk_records, "hk_bills", model, db)
        total_chunks += n
        print(f"   ✅ 写入 {n} 个向量块 → collection 'hk_bills'")
    else:
        print(f"\nℹ️  跳过香港数据")

    # ── 总览 ──
    print("\n" + "=" * 60)
    print("向量库构建完成")
    print("=" * 60)
    print(f"  存储路径: {db_path.resolve()}")
    print(f"  总向量块: {total_chunks}")
    print(f"  Collections: {db.list_collections()}")
    print()


if __name__ == "__main__":
    main()
