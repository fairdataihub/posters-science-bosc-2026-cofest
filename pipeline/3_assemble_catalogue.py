"""Capstone: turn the enriched DeepSeek catalogue into two deliverables.

Collapse tiers (biomarker name -> canonical entity):
  T1 character  charkey (NFKC+casefold+strip punct)         "IL6"/"IL-6" -> same
  T2 semantic   fairly synonym-lustre (gte + HDBSCAN, holdout)  spelling variants
  T3 alias      DeepSeek acronym/synonym dictionary          "IL-6" <-> "interleukin-6"
Then each canonical entity is matched (by ALL its surface forms) against the known
BiomarkerKB list -> exact | partial | none  ('none' = candidate novel marker).

Outputs:
  posters-2024plus.biomarkers-counts.csv     one row per canonical entity + match
  posters-2024plus.biomarker-catalogue.csv   long: one row per poster x biomarker x condition
  posters-2024plus.biomarkers-index.json     machine-readable summary
"""
import json, csv, re, unicodedata
from collections import Counter, defaultdict
from fairly import Normalizer
from fairly.config import FieldConfig
from fairly.presets import SUBJECT_CLEANER
import match_known as MK

SCR = "/home/jme/scratch_ptf"
CAT = f"{SCR}/deepseek_catalogue.jsonl"
OUT_COUNTS = "/home/jme/Downloads/posters-2024plus.biomarkers-counts.csv"
OUT_CAT = "/home/jme/Downloads/posters-2024plus.biomarker-catalogue.csv"
OUT_JSON = "/home/jme/Downloads/posters-2024plus.biomarkers-index.json"

def charkey(s):
    s = unicodedata.normalize("NFKC", str(s)).casefold().strip()
    return re.sub(r"[\s\-_/]+", "", s)

# ---- load enriched catalogue ----
recs = [json.loads(l) for l in open(CAT)]
occ = []   # flat occurrences
name_posters = defaultdict(set); name_mentions = Counter()
key_surface = defaultdict(Counter)   # charkey -> Counter(original surface form)
for r in recs:
    pid = r["id"]
    for b in r.get("biomarkers", []):
        nm = (b.get("name") or "").strip()
        if not nm:
            continue
        occ.append((r, b))
        name_mentions[nm] += 1; name_posters[nm].add(pid)
        for s in [nm, b.get("acronym")] + (b.get("synonyms") or []):
            if s and str(s).strip():
                key_surface[charkey(s)][str(s).strip()] += name_mentions[nm]
print(f"catalogue posters: {len(recs)} | biomarker occurrences: {len(occ)} | distinct names: {len(name_mentions)}")

# ---- union-find over charkeys ----
parent = {}
def find(x):
    parent.setdefault(x, x)
    while parent[x] != x:
        parent[x] = parent[parent[x]]; x = parent[x]
    return x
def union(a, b):
    ra, rb = find(a), find(b)
    if ra != rb: parent[ra] = rb

for k in key_surface:            # ensure nodes
    find(k)

# T2 semantic: fairly over distinct NAME charkeys (canonical surface per key)
name_key_counts = Counter()
for nm, c in name_mentions.items():
    name_key_counts[charkey(nm)] += c
cfg = FieldConfig(name="biomarker", strategy="semantic", eps=0.08, holdout=True,
                  authority=None, cleaner=SUBJECT_CLEANER)
norm = Normalizer(cfg, cache_dir=f"{SCR}/.fairly_cache")
# fairly works on surface strings; feed the most-frequent surface per key
key_repr = {k: key_surface[k].most_common(1)[0][0] for k in name_key_counts}
repr_counts = {key_repr[k]: name_key_counts[k] for k in name_key_counts}
smap = norm.build(repr_counts)
for variant, canon in (smap.mapping.items() if hasattr(smap, "mapping") else []):
    union(charkey(variant), charkey(canon))
print(f"T2 fairly merges: {len(getattr(smap,'mapping',{}))}")

# T3 alias: link name<->acronym<->synonyms from every occurrence
alias_links = 0
for _, b in occ:
    nm = (b.get("name") or "").strip()
    if not nm:
        continue
    nk = charkey(nm)
    for s in [b.get("acronym")] + (b.get("synonyms") or []):
        if s and str(s).strip():
            union(nk, charkey(s)); alias_links += 1
print(f"T3 alias links: {alias_links}")

# ---- resolve canonical entity per component ----
comp_keys = defaultdict(list)
for k in list(parent.keys()):
    comp_keys[find(k)].append(k)
# canonical surface = most frequent NAME surface in the component
def comp_canonical(keys):
    cnt = Counter()
    for k in keys:
        for surf, c in key_surface[k].items():
            cnt[surf] += c
    return cnt.most_common(1)[0][0] if cnt else keys[0]
key2canon = {}
comp_surface = {}
for root, keys in comp_keys.items():
    canon = comp_canonical(keys)
    comp_surface[root] = sorted({s for k in keys for s in key_surface[k]})
    for k in keys:
        key2canon[k] = canon
def canon_of(name): return key2canon.get(charkey(name), name.strip())

# ---- known-DB match per canonical entity (use ALL its surface forms) ----
KB = MK.load_known()
canon_match = {}
for root, keys in comp_keys.items():
    canon = key2canon[keys[0]]
    surfaces = comp_surface[root]
    status, ent, conds = MK.classify(surfaces, KB)
    canon_match[canon] = {"status": status, "known": ent, "known_conditions": conds,
                          "surfaces": surfaces}

# ---- aggregate counts per canonical ----
c_posters = defaultdict(set); c_mentions = Counter()
c_kind = defaultdict(Counter); c_status = defaultdict(Counter)
c_conditions = defaultdict(Counter); c_specimen = defaultdict(Counter)
for r, b in occ:
    canon = canon_of(b.get("name") or "")
    c_posters[canon].add(r["id"]); c_mentions[canon] += 1
    if b.get("kind"): c_kind[canon][b["kind"]] += 1
    if b.get("status"): c_status[canon][b["status"]] += 1
    for cond in (b.get("conditions") or []):
        if cond: c_conditions[canon][cond] += 1
    if b.get("specimen"): c_specimen[canon][b["specimen"]] += 1

rows = sorted(c_mentions, key=lambda c: (-len(c_posters[c]), -c_mentions[c]))
with open(OUT_COUNTS, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["canonical", "posters", "mentions", "kind", "status", "match_status",
                "matched_known_entity", "known_conditions", "top_conditions",
                "n_surface_forms", "surface_forms"])
    for canon in rows:
        m = canon_match.get(canon, {"status": "none", "known": "", "known_conditions": [], "surfaces": [canon]})
        w.writerow([
            canon, len(c_posters[canon]), c_mentions[canon],
            (c_kind[canon].most_common(1)[0][0] if c_kind[canon] else ""),
            (c_status[canon].most_common(1)[0][0] if c_status[canon] else ""),
            m["status"], m["known"] or "", "; ".join(m["known_conditions"]),
            "; ".join(f"{k}({v})" for k, v in c_conditions[canon].most_common(3)),
            len(m["surfaces"]), "; ".join(m["surfaces"]),
        ])

# ---- long catalogue: one row per poster x biomarker x condition ----
with open(OUT_CAT, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["poster_id", "doi", "url", "year", "field", "subfield",
                "biomarker_canonical", "name_as_used", "acronym", "synonyms", "kind",
                "condition", "specimen", "role", "direction", "method", "population",
                "status", "match_status", "matched_known_entity", "evidence", "title"])
    for r, b in occ:
        canon = canon_of(b.get("name") or "")
        mm = canon_match.get(canon, {})
        conds = b.get("conditions") or [""]
        for cond in conds:
            w.writerow([
                r["id"], r.get("doi", ""), r.get("url", ""), r.get("year", ""),
                r.get("field", ""), r.get("subfield", ""),
                canon, b.get("name", ""), b.get("acronym") or "",
                "; ".join(b.get("synonyms") or []), b.get("kind", ""),
                cond, b.get("specimen") or "", b.get("role", ""), b.get("direction", ""),
                b.get("method") or "", b.get("population") or "", b.get("status", ""),
                mm.get("status", ""), mm.get("known", "") or "", b.get("evidence", ""),
                (r.get("title") or "")[:200],
            ])

# ---- summary ----
match_dist = Counter(canon_match[c]["status"] for c in rows)
json.dump({
    "catalogue_posters": len(recs), "biomarker_occurrences": len(occ),
    "distinct_raw_names": len(name_mentions), "canonical_entities": len(rows),
    "match_distribution": dict(match_dist),
    "novel_no_match": [c for c in rows if canon_match[c]["status"] == "none"][:2000],
}, open(OUT_JSON, "w"), indent=1)

print(f"\ncanonical entities: {len(rows)} (from {len(name_mentions)} raw names)")
print(f"match distribution: {dict(match_dist)}")
print(f"  -> {OUT_COUNTS}\n  -> {OUT_CAT}\n  -> {OUT_JSON}")
print("\ntop 20 by posters (match_status):")
for c in rows[:20]:
    m = canon_match[c]
    print(f"  {len(c_posters[c]):3d}p {c_mentions[c]:3d}m  [{m['status']:7s}]  {c}"
          + (f"  ~{m['known']}" if m['known'] else ""))
print("\nsample NO-MATCH (candidate novel):")
nm_rows = [c for c in rows if canon_match[c]["status"] == "none"]
for c in nm_rows[:25]:
    print(f"  {len(c_posters[c]):3d}p  {c}  ({c_kind[c].most_common(1)[0][0] if c_kind[c] else '?'})")
