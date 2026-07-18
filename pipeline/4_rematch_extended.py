"""Re-match the assembled canonical biomarkers against the EXTENDED reference
(BiomarkerKB + MarkerDB, HGNC alias-normalized) without re-embedding — reuses the
surface_forms already in biomarkers-counts.csv. Opportunistically folds in the
seeded pass's standard IDs / canonical names / aliases when available.

Writes biomarkers-counts-v2.csv and prints old vs new match distribution.
"""
import csv, json, os
from collections import Counter
import match_known2 as MK

SCR = "/home/jme/scratch_ptf"
IN = "/home/jme/Downloads/posters-2024plus.biomarkers-counts.csv"
OUT = "/home/jme/Downloads/posters-2024plus.biomarkers-counts-v2.csv"
SEEDED = f"{SCR}/deepseek_seeded.jsonl"
MOL = {"gene","protein","transcript","miRNA","metabolite","mutation","signature","lipid"}

def ckey(s):
    return MK.charkey(s)

# seeded extras: charkey(seed/canonical name) -> set(extra surface forms incl standard_id)
seed_extra = {}
n_seed = 0
if os.path.exists(SEEDED):
    for l in open(SEEDED):
        for b in json.loads(l).get("biomarkers", []):
            names = [b.get("seed_name"), b.get("canonical_name")] + (b.get("aliases") or [])
            sid = b.get("standard_id")
            extras = {x for x in ([b.get("canonical_name"), sid] + (b.get("aliases") or [])) if x and str(x).strip()}
            for nm in names:
                if nm and str(nm).strip() and nm != "NEW":
                    seed_extra.setdefault(ckey(nm), set()).update(extras)
                    n_seed += 1
print(f"loaded {len(seed_extra)} seeded name->extras ({'partial' if not os.path.exists(SEEDED) or True else ''})")

KB = MK.load_refs()
print(f"reference keys: {len(KB['known'])}")

rows = list(csv.DictReader(open(IN)))
old = Counter(r["match_status"] for r in rows)
new = Counter(); new_mol = Counter()
flipped = []

fieldnames = list(rows[0].keys())
for c in ("match_status", "matched_known_entity", "match_source", "known_conditions"):
    if c not in fieldnames:
        fieldnames.append(c)

with open(OUT, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    for r in rows:
        surfaces = [s.strip() for s in (r.get("surface_forms") or "").split(";") if s.strip()]
        surfaces.append(r["canonical"])
        for s in list(surfaces):
            surfaces += list(seed_extra.get(ckey(s), []))
        status, disp, src, conds = MK.classify(surfaces, KB)
        if status != r["match_status"]:
            flipped.append((r["canonical"], r["match_status"], status, src))
        r["match_status"] = status
        r["matched_known_entity"] = disp or ""
        r["match_source"] = src or ""
        r["known_conditions"] = "; ".join(conds)
        new[status] += 1
        if r.get("kind") in MOL:
            new_mol[status] += 1
        w.writerow(r)

tot = sum(new.values())
print(f"\n{'':10s}{'OLD':>18s}{'NEW (BiomarkerKB+MarkerDB+HGNC)':>34s}")
for k in ("exact", "partial", "none"):
    print(f"  {k:8s}{old[k]:6d} ({100*old[k]/tot:.0f}%)      {new[k]:6d} ({100*new[k]/tot:.0f}%)")
print(f"\nMOLECULAR-only NEW: " + ", ".join(f"{k}={new_mol[k]}" for k in ("exact","partial","none"))
      + f"  (none was {sum(1 for r in rows if r.get('kind') in MOL and r['match_status'])});")
n2n = sum(1 for c,o,nw,s in flipped if o=='none' and nw!='none')
print(f"'none' -> matched (newly explained): {n2n}")
print(f"total status changes: {len(flipped)}")
print("\nsample none->exact (known markers we were missing):")
for c,o,nw,s in [x for x in flipped if x[1]=='none' and x[2]=='exact'][:15]:
    print(f"  {c:35s} -> {s}")
print(f"\n-> {OUT}")
