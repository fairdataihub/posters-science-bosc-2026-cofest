"""Corpus-wide condition frequency across the Health+Life subset (~2,930 posters):
combine conditions from the biomarker catalogue (1,368) with the condition-only
pass over the biomarker-negative posters (1,562). One condition counted once per
poster (document frequency). Character-normalized + matched to BiomarkerKB's DOID
condition list where possible. Broken out by year to show cross-conference trends.
"""
import json, csv, re, unicodedata
from collections import Counter, defaultdict

SCR = "/home/jme/scratch_ptf"
CAT = f"{SCR}/deepseek_catalogue.jsonl"
CONDS = f"{SCR}/deepseek_conditions.jsonl"
KNOWN = "/home/jme/Downloads/biomarker_list.csv"
OUT_CSV = "/home/jme/Downloads/posters-2024plus.condition-frequency.csv"
OUT_JSON = "/home/jme/Downloads/posters-2024plus.condition-frequency.json"

def norm_cond(s):
    s = unicodedata.normalize("NFKC", str(s)).strip()
    s = re.sub(r"\s*\((?:DOID|MONDO|HP)[:_]\d+\)\s*", "", s, flags=re.I)  # strip ontology tag
    s = re.sub(r"\s+", " ", s).strip().rstrip(".")
    return s
def key(s):
    return re.sub(r"[^a-z0-9]+", "", unicodedata.normalize("NFKC", str(s)).casefold())

# --- known DB conditions (name + DOID) for canonicalization ---
known = {}   # key -> display name (with ontology id)
for row in csv.DictReader(open(KNOWN)):
    c = (row.get("condition") or "").strip()
    if c:
        base = norm_cond(c)
        known.setdefault(key(base), c)   # keep first (has the DOID tag)

# --- per-poster condition sets + year, from both sources ---
poster_conds = defaultdict(set)
poster_year = {}
poster_src = {}
for l in open(CAT):
    d = json.loads(l); pid = d["id"]; poster_year[pid] = d.get("year"); poster_src[pid] = "biomarker"
    for b in d.get("biomarkers", []):
        for c in (b.get("conditions") or []):
            if c and str(c).strip():
                poster_conds[pid].add(norm_cond(c))
for l in open(CONDS):
    d = json.loads(l); pid = d["id"]; poster_year[pid] = d.get("year"); poster_src.setdefault(pid, "no-biomarker")
    for c in (d.get("conditions") or []):
        if c and str(c).strip():
            poster_conds[pid].add(norm_cond(c))

# --- aggregate: canonical condition -> posters, split, year histogram ---
canon_display = {}
posters = defaultdict(set)
by_year = defaultdict(Counter)
split = defaultdict(lambda: Counter())
for pid, conds in poster_conds.items():
    seen_keys = set()
    for c in conds:
        k = key(c)
        if not k or k in seen_keys:
            continue
        seen_keys.add(k)
        canon_display.setdefault(k, known.get(k, c))     # prefer known DOID-tagged name
        posters[k].add(pid)
        if poster_year.get(pid):
            by_year[k][int(poster_year[pid])] += 1
        split[k][poster_src.get(pid, "?")] += 1

rows = sorted(posters, key=lambda k: -len(posters[k]))
with open(OUT_CSV, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["condition", "posters", "from_biomarker_posters", "from_other_posters",
                "in_known_db", "by_year"])
    for k in rows:
        yrs = dict(sorted(by_year[k].items()))
        w.writerow([canon_display[k], len(posters[k]), split[k]["biomarker"],
                    split[k]["no-biomarker"], "yes" if k in known else "no",
                    "; ".join(f"{y}:{n}" for y, n in yrs.items())])

total_posters_with_cond = len({p for ks in posters.values() for p in ks})
json.dump({
    "posters_with_a_condition": total_posters_with_cond,
    "distinct_conditions": len(rows),
    "top_conditions": [{"condition": canon_display[k], "posters": len(posters[k]),
                        "in_known_db": k in known} for k in rows[:200]],
}, open(OUT_JSON, "w"), indent=1)

print(f"posters with >=1 condition: {total_posters_with_cond}")
print(f"distinct conditions: {len(rows)}")
print(f"-> {OUT_CSV}\n-> {OUT_JSON}")
print("\ntop 30 conditions across the biomedical corpus (posters):")
for k in rows[:30]:
    kb = "  [in known DB]" if k in known else "  [NOT in known DB]"
    print(f"  {len(posters[k]):4d}  {canon_display[k][:55]:55s}{kb}")
