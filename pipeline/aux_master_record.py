"""Stage 11: join every layer into one master record per poster (the 11,028 2024+
posters). Resilient — attaches whatever passes have finished; missing layers are
simply absent. Writes posters-2024plus-master.ndjson + a small coverage report.

Layers joined (by poster id):
  classification  annotations.jsonl + topic_assign.json        (all 11,028)
  biomarkers      deepseek_catalogue.jsonl (enriched)           (~1,368)
    + match       biomarkers-counts.csv  (canonical, exact/partial/none)
    + std ids     deepseek_seeded.jsonl  (HGNC/UniProt/CHEBI)   (optional)
  conditions      catalogue biomarkers' conditions ∪ deepseek_conditions.jsonl
"""
import json, csv, glob, os, re, unicodedata
from collections import defaultdict

SCR = "/home/jme/scratch_ptf"
SRC = "/home/jme/Downloads/posters-export"
DL = "/home/jme/Downloads"
OUT = f"{DL}/posters-2024plus-master.ndjson"

def key(s):
    return re.sub(r"[^a-z0-9]+", "", unicodedata.normalize("NFKC", str(s)).casefold())
def load_jsonl(p):
    return {json.loads(l)["id"]: json.loads(l) for l in open(p)} if os.path.exists(p) else {}

ann = load_jsonl(f"{SCR}/annotations.jsonl")
topic = json.load(open(f"{SCR}/topic_assign.json"))["meta"] if os.path.exists(f"{SCR}/topic_assign.json") else {}
F2D = {t["field_id"]: t["domain"] for t in json.load(open(f"{SCR}/openalex_topics.json"))}
catalogue = load_jsonl(f"{SCR}/deepseek_catalogue.jsonl")
conditions_pass = load_jsonl(f"{SCR}/deepseek_conditions.jsonl")
seeded = load_jsonl(f"{SCR}/deepseek_seeded.jsonl")

# canonical -> reason_code from the methodical none-classification (stage 13/13b)
reason_by_canon = {}
rc_csv = f"{DL}/posters-2024plus.none-classified-final.csv"
if os.path.exists(rc_csv):
    for row in csv.DictReader(open(rc_csv)):
        reason_by_canon[key(row["canonical"])] = row.get("reason_code", "")

# surface-form -> {canonical, match_status, matched_known, match_source, reason} from counts-v2
surf2match = {}
counts_csv = f"{DL}/posters-2024plus.biomarkers-counts-v2.csv"
if not os.path.exists(counts_csv):
    counts_csv = f"{DL}/posters-2024plus.biomarkers-counts.csv"
if os.path.exists(counts_csv):
    for row in csv.DictReader(open(counts_csv)):
        info = {"canonical": row["canonical"], "match_status": row["match_status"],
                "matched_known_entity": row.get("matched_known_entity", ""),
                "match_source": row.get("match_source", ""),
                "reason_code": reason_by_canon.get(key(row["canonical"]), "")}
        surf2match[key(row["canonical"])] = info
        for s in (row.get("surface_forms") or "").split(";"):
            if s.strip():
                surf2match.setdefault(key(s), info)

# seeded standard-id map: (poster id, key(seed_name)) -> {standard_id, id_source, canonical_name}
seed_ids = {}
for pid, rec in seeded.items():
    for b in rec.get("biomarkers", []):
        sn = b.get("seed_name") or b.get("canonical_name") or ""
        if sn and sn != "NEW":
            seed_ids[(pid, key(sn))] = {
                "standard_id": b.get("standard_id"), "id_source": b.get("id_source"),
                "canonical_name": b.get("canonical_name")}

def creators_of(pj):
    out = []
    for c in (pj.get("creators") or [])[:20]:
        nm = c.get("name")
        if nm: out.append(nm)
    return out

n = 0
cover = defaultdict(int)
with open(OUT, "w") as outf:
    for fp in sorted(glob.glob(f"{SRC}/*.ndjson")):
        for ln in open(fp):
            if not ln.strip(): continue
            d = json.loads(ln); rid = str(d["id"])
            a = ann.get(rid)
            if not a:                      # not in the 2024+ classified set
                continue
            pj = d["posterJson"]
            if isinstance(pj, str): pj = json.loads(pj)
            layers = ["classification"]

            rec = {
                "id": rid, "doi": pj.get("doi"), "url": d.get("posterUrl"),
                "title": (pj.get("titles") or [{}])[0].get("title", ""),
                "year": pj.get("publicationYear") or (pj.get("conference") or {}).get("conferenceYear"),
                "creators": creators_of(pj),
                "conference": (pj.get("conference") or {}).get("conferenceName"),
                "classification": {
                    "field": a["field"], "domain": F2D.get(a["field_id"]),
                    "field_score": a.get("field_score"),
                    "subfield": topic.get(rid, {}).get("subfield"),
                    "topic": topic.get(rid, {}).get("topic"),
                },
            }

            # biomarkers (enriched catalogue) + match + std id
            bms = []
            conds = set()
            cat = catalogue.get(rid)
            if cat:
                layers.append("biomarkers")
                for b in cat.get("biomarkers", []):
                    nm = (b.get("name") or "").strip()
                    if not nm: continue
                    m = surf2match.get(key(nm), {})
                    sid = seed_ids.get((rid, key(nm)), {})
                    for c in (b.get("conditions") or []):
                        if c: conds.add(str(c).strip())
                    bms.append({
                        "name": nm, "canonical": m.get("canonical", nm),
                        "acronym": b.get("acronym"), "synonyms": b.get("synonyms") or [],
                        "kind": b.get("kind"), "status": b.get("status"), "role": b.get("role"),
                        "direction": b.get("direction"), "specimen": b.get("specimen"),
                        "method": b.get("method"), "population": b.get("population"),
                        "conditions": b.get("conditions") or [], "evidence": b.get("evidence"),
                        "match_status": m.get("match_status"),
                        "matched_known_entity": m.get("matched_known_entity"),
                        "match_source": m.get("match_source"),
                        "reason_code": m.get("reason_code"),
                        "standard_id": sid.get("standard_id"), "id_source": sid.get("id_source"),
                    })
                if any(b.get("match_status") for b in bms): layers.append("biomarker_match")
                if any(b.get("standard_id") for b in bms): layers.append("standard_ids")
            rec["biomarkers"] = bms

            # conditions (union: catalogue biomarker conditions ∪ condition-only pass)
            cp = conditions_pass.get(rid)
            if cp:
                layers.append("conditions")
                for c in (cp.get("conditions") or []):
                    if c: conds.add(str(c).strip())
            rec["conditions"] = sorted(conds)

            rec["_layers"] = layers
            for L in layers: cover[L] += 1
            outf.write(json.dumps(rec, ensure_ascii=False) + "\n"); n += 1

print(f"master records written: {n} -> {OUT}")
print("layer coverage:")
for L, c in sorted(cover.items(), key=lambda x: -x[1]):
    print(f"  {c:6d}  {L}")
