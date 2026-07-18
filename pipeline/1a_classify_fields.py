"""paper-to-field inference over the full posters export.
Annotates every record (no filtering). Saves field predictions + [CLS] embeddings
so topic nearest-neighbour can be attached afterwards.
Run: ~/.venvs/torch-pascal/bin/python infer.py
"""
import json, glob, time, numpy as np, torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

M = "jimnoneill/paper-to-field"
SNAP = "/home/jme/.cache/huggingface/hub/models--jimnoneill--paper-to-field/snapshots/3ee629274016a7e9573e36a12c23bedd1e39b6db"
SRC = "/home/jme/Downloads/posters-export"
OUT = "/home/jme/scratch_ptf"
BATCH = 32
MAXLEN = 384

dev = "cuda" if torch.cuda.is_available() else "cpu"
tok = AutoTokenizer.from_pretrained(M)
# NB: fp32 on purpose. This is a Pascal GTX 1070 (sm_61) whose native fp16 runs at
# 1/64 rate — .half() makes it ~5x SLOWER here, not faster. Keep full precision.
# We call model.electra (encoder) + model.classifier directly rather than passing
# output_hidden_states=True, which would retain all 24 layers and OOM the 8GB card.
model = AutoModelForSequenceClassification.from_pretrained(M).to(dev).eval()
id2name = model.config.id2label                       # model-idx -> field name
idx2oaid = json.load(open(f"{SNAP}/label_mappings.json"))["idx_to_label"]  # model-idx -> OpenAlex field id

MIN_YEAR = 2024   # only classify posters from 2024 to present (pre-filter, saves GPU)

def text_of(pj):
    ts = pj.get("titles") or []
    title = ts[0].get("title","") if ts else ""
    desc = " ".join((d.get("description","") or "") for d in (pj.get("descriptions") or []))
    c = pj.get("content")
    content = c if isinstance(c,str) else (json.dumps(c) if c else "")
    return f"{title}. {desc} {content}".strip()

def year_of(pj):
    return pj.get("publicationYear") or (pj.get("conference") or {}).get("conferenceYear")

# load records from MIN_YEAR onward (id, doi, text)
records = []; skipped = 0
for fp in sorted(glob.glob(f"{SRC}/*.ndjson")):
    for ln in open(fp):
        if not ln.strip(): continue
        d = json.loads(ln); pj = d["posterJson"]
        if isinstance(pj, str): pj = json.loads(pj)
        y = year_of(pj)
        if not y or int(y) < MIN_YEAR:
            skipped += 1; continue
        records.append((str(d["id"]), pj.get("doi"), text_of(pj)))
print(f"records >= {MIN_YEAR}: {len(records)} | skipped {skipped} | device: {dev}", flush=True)

ann = open(f"{OUT}/annotations.jsonl", "w")
emb_all = np.empty((len(records), model.config.hidden_size), dtype=np.float32)
t0 = time.time()
for i in range(0, len(records), BATCH):
    chunk = records[i:i+BATCH]
    enc = tok([r[2] for r in chunk], truncation=True, max_length=MAXLEN,
              padding=True, return_tensors="pt").to(dev)
    with torch.no_grad():
        seq = model.electra(**enc).last_hidden_state      # (B, T, H) — only last layer
        logits = model.classifier(seq)                     # ElectraClassificationHead uses [:,0]
    probs = logits.softmax(-1)
    cls = seq[:, 0, :].cpu().numpy()
    emb_all[i:i+len(chunk)] = cls
    for j, (rid, doi, _) in enumerate(chunk):
        p = probs[j]
        top = torch.topk(p, 3)
        best = int(top.indices[0])
        ann.write(json.dumps({
            "id": rid, "doi": doi,
            "field_id": int(idx2oaid[str(best)]),
            "field": id2name[best],
            "field_score": round(float(top.values[0]), 4),
            "top3": [[id2name[int(k)], round(float(v), 4)]
                     for k, v in zip(top.indices, top.values)],
        }) + "\n")
    if (i // BATCH) % 50 == 0:
        el = time.time() - t0
        print(f"  {i+len(chunk)}/{len(records)}  ({el:.0f}s, {(i+len(chunk))/max(el,1):.0f} rec/s)", flush=True)
ann.close()
np.save(f"{OUT}/cls_embeddings.npy", emb_all)
json.dump([r[0] for r in records], open(f"{OUT}/ids.json", "w"))
print(f"done: {len(records)} in {time.time()-t0:.0f}s -> annotations.jsonl + cls_embeddings.npy", flush=True)
