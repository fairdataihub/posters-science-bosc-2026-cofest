"""Attach OpenAlex topic (name/subfield/field/domain) to each poster via
nearest-neighbour of its [CLS] embedding against topic_embeddings.npy.

First VALIDATES the unknown row-order of topic_embeddings.npy by checking, for a
sample, whether each poster's nearest topic falls in the classifier's predicted
field. The ordering with the best agreement wins; if none clears chance, topic-NN
is not trustworthy and we ship field-level only.
"""
import json, numpy as np

OUT = "/home/jme/scratch_ptf"
SNAP = "/home/jme/.cache/huggingface/hub/models--jimnoneill--paper-to-field/snapshots/3ee629274016a7e9573e36a12c23bedd1e39b6db"

emb = np.load(f"{OUT}/cls_embeddings.npy").astype(np.float32)
emb /= (np.linalg.norm(emb, axis=1, keepdims=True) + 1e-8)
ids = json.load(open(f"{OUT}/ids.json"))
topic_emb = np.load(f"{SNAP}/topic_embeddings.npy").astype(np.float32)
topic_emb /= (np.linalg.norm(topic_emb, axis=1, keepdims=True) + 1e-8)
topics = json.load(open(f"{OUT}/openalex_topics.json"))   # API-default order
ann = [json.loads(l) for l in open(f"{OUT}/annotations.jsonl")]
field_of = {a["id"]: a["field_id"] for a in ann}
assert len(topics) == topic_emb.shape[0] == 4516

# candidate row orderings of topic_emb -> topic metadata
orderings = {
    "api_default": topics,
    "tid_asc": sorted(topics, key=lambda t: t["tid"]),
}

rng = np.random.default_rng(0)
samp = rng.choice(len(ids), size=min(2000, len(ids)), replace=False)
S = emb[samp]                                   # (n,1024)
sim = S @ topic_emb.T                            # (n,4516) cosine
nn = sim.argmax(1)                               # nearest topic row per sample

print("row-order validation (agreement of nearest-topic field vs classifier field):")
best = None
for name, order in orderings.items():
    row_field = np.array([order[r]["field_id"] for r in nn])
    clf_field = np.array([field_of[ids[i]] for i in samp])
    agree = float((row_field == clf_field).mean())
    print(f"  {name:12s}: {agree:.3f}")
    if best is None or agree > best[1]:
        best = (name, agree, order)

name, agree, order = best
print(f"\nchosen ordering: {name} (agreement {agree:.3f})")
if agree < 0.30:
    print("WARNING: agreement near chance — topic-NN embeddings may be incompatible; "
          "shipping field-level annotation only.")
    import sys; sys.exit(2)

# full assignment (batched to bound memory)
meta = []
B = 4000
for i in range(0, emb.shape[0], B):
    sub = emb[i:i+B] @ topic_emb.T
    j = sub.argmax(1)
    sc = sub[np.arange(sub.shape[0]), j]
    for k, r in enumerate(j):
        t = order[int(r)]
        meta.append({"topic": t["name"], "topic_id": t["tid"],
                     "subfield": t["subfield"], "topic_field": t["field"],
                     "domain": t["domain"], "topic_sim": round(float(sc[k]), 4)})
json.dump({"order": name, "agreement": agree, "meta": dict(zip(ids, meta))},
          open(f"{OUT}/topic_assign.json", "w"))
print(f"assigned topics for {len(meta)} posters -> topic_assign.json")
# quick peek: top subfields
from collections import Counter
c = Counter(m["subfield"] for m in meta)
print("top subfields:", c.most_common(12))
