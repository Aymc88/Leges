#!/usr/bin/env python3
"""Embed all bills using Deepseek API, save as .npy"""
import json, httpx, os, time, numpy as np, sys

records = []
for fname in ["ca_bills.jsonl", "hk_bills.jsonl", "mo_laws.jsonl"]:
    with open(f"output/{fname}") as f:
        for line in f:
            records.append(json.loads(line))
print(f"Total: {len(records)} bills")

api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
embeddings, metadata = [], []
batch_size = 20

for i in range(0, len(records), batch_size):
    batch = records[i:i+batch_size]
    texts = [((r.get("title","") or "") + " " + (r.get("description","") or "")).strip() or (r.get("title","") or "") for r in batch]

    resp = httpx.post(
        "https://api.deepseek.com/v1/embeddings",
        json={"model": "text-embedding-v3", "input": texts},
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        timeout=60,
    )
    data = resp.json()
    if "data" not in data:
        print(f"ERROR at batch {i}: {data}")
        continue
    for j, r in enumerate(batch):
        vec = data["data"][j]["embedding"]
        embeddings.append(vec)
        metadata.append({
            "bill_id": r.get("bill_id") or f"MO-{r.get('law_id','')}",
            "jurisdiction": r.get("jurisdiction", ""),
            "title": (r.get("title","") or "")[:200],
            "status": r.get("status", ""),
            "passed": r.get("passed"),
            "subject": r.get("subject", ""),
        })
    print(f"  {i+len(batch)}/{len(records)} - dim={len(vec)}")
    time.sleep(0.3)

np.save("data/embeddings_deepseek.npy", np.array(embeddings, dtype=np.float32))
with open("data/bill_metadata.json", "w") as f:
    json.dump(metadata, f, ensure_ascii=False)
dim = len(embeddings[0]) if embeddings else 0
print(f"DONE! {len(embeddings)} embeddings, dim={dim}")
