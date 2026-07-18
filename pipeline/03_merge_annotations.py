"""Final step: annotate every original export record with its paper-to-field
result (field + topic) and write the fully-labeled corpus. Nothing is filtered.
Also writes a biomedical-field convenience view as a starting point for
downstream biomarker discovery (clearly a superset, not a biomarker filter).
"""
import json, glob, zipfile, os
import numpy as np

SCR = "/home/jme/scratch_ptf"
SRC = "/home/jme/Downloads/posters-export"
# infer.py already restricted to publicationYear >= 2024, so these are the 2024+ set.
DEST = "/home/jme/Downloads/posters-2024plus-annotated.ndjson"       # all classified, all domains
DEST_BIO = "/home/jme/Downloads/posters-2024plus-biomedical.ndjson"  # Health+Life domains — PRIMARY
DEST_ZIP = "/home/jme/Downloads/posters-2024plus-biomedical.zip"     # zip the deliverable

fields = {json.loads(l)["id"]: json.loads(l) for l in open(f"{SCR}/annotations.jsonl")}
# deterministic field_id -> domain (OpenAlex hierarchy), so domain is always present
F2D = {t["field_id"]: t["domain"] for t in json.load(open(f"{SCR}/openalex_topics.json"))}
topics = {}
tinfo = {}
tpath = f"{SCR}/topic_assign.json"
if os.path.exists(tpath):
    tj = json.load(open(tpath))
    topics = tj["meta"]; tinfo = {"order": tj["order"], "agreement": tj["agreement"]}
    print(f"topic assignment present (order={tinfo['order']}, agreement={tinfo['agreement']:.2f})")
else:
    print("no topic assignment — writing field-level annotation only")

# OpenAlex biomedical fields (field_id) — a broad biomedical superset, NOT a biomarker filter.
# 11 Agri & Biological Sci, 13 Biochem/Genetics/MolBio, 24 Immunology & Microbiology,
# 27 Medicine, 28 Neuroscience, 29 Nursing, 30 Pharmacology/Toxicology/Pharmaceutics,
# 34 Veterinary, 35 Dentistry, 36 Health Professions.
BIOMED = {11, 13, 24, 27, 28, 29, 30, 34, 35, 36}

n = 0; nbio = 0
out = open(DEST, "w"); outb = open(DEST_BIO, "w")
for fp in sorted(glob.glob(f"{SRC}/*.ndjson")):
    for ln in open(fp):
        if not ln.strip():
            continue
        d = json.loads(ln)
        rid = str(d["id"])
        f = fields.get(rid)
        if not f:
            continue
        ann = {"field": f["field"], "field_id": f["field_id"],
               "domain": F2D[f["field_id"]],           # from field: always present
               "field_score": f["field_score"], "top3_fields": f["top3"]}
        t = topics.get(rid)
        if t:
            ann.update({"topic": t["topic"], "topic_id": t["topic_id"],
                        "subfield": t["subfield"], "topic_sim": t["topic_sim"]})
        d["_paper_to_field"] = ann
        line = json.dumps(d, ensure_ascii=False) + "\n"
        out.write(line); n += 1
        if f["field_id"] in BIOMED:
            outb.write(line); nbio += 1
out.close(); outb.close()
print(f"annotated {n} records -> {DEST}")
print(f"biomedical-field subset: {nbio} -> {DEST_BIO}")

with zipfile.ZipFile(DEST_ZIP, "w", zipfile.ZIP_DEFLATED) as z:
    z.write(DEST_BIO, arcname="posters-2024plus-biomedical.ndjson")
print(f"zipped deliverable -> {DEST_ZIP} ({os.path.getsize(DEST_ZIP)/1e6:.1f} MB)")

# manifest of counts so any cut can be chosen without re-running
from collections import Counter
dom = Counter(F2D[f["field_id"]] for f in fields.values())
fld = Counter(f["field"] for f in fields.values())
sub = Counter(topics[i]["subfield"] for i in fields if i in topics) if topics else Counter()
manifest = {"total": n, "biomedical_health_life": nbio,
            "by_domain": dict(dom.most_common()),
            "by_field": dict(fld.most_common()),
            "by_subfield_top40": dict(sub.most_common(40)),
            "topic_order": tinfo}
manifest["min_year"] = 2024
json.dump(manifest, open("/home/jme/Downloads/posters-2024plus.manifest.json", "w"), indent=1)

print(f"\ndomain distribution (all {n}):")
for d, k in dom.most_common():
    print(f"  {k:6d}  {100*k/n:4.1f}%  {d}")
print("field distribution:")
for name, k in fld.most_common():
    print(f"  {k:6d}  {name}")
if sub:
    print("top subfields (finer biomarker-style filtering handle):")
    for name, k in sub.most_common(15):
        print(f"  {k:6d}  {name}")
