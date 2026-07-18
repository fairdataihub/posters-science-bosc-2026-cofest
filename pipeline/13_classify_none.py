"""Stage 13: methodically parse the 'none' category into reason codes.

Cascade (cheap -> expensive):
  1. kind gate         non-molecular kinds -> NOT_ENTITY (covariate/organism/imaging/...)
  2. rule signals      biosensor/tool + generic term            -> NOT_ENTITY
  3. ID resolution     seeded standard_id, or HGNC/Ensembl gene -> KNOWN_UNCATALOGUED
  4. -> AMBIGUOUS      molecular, no ID, not obviously junk     -> LLM adjudication (stage 13b)

Writes none-classified.csv with reason_code + signals. The AMBIGUOUS rows are
written to none_ambiguous.json for the DeepSeek adjudication pass (classify_none_llm.py).
"""
import csv, json, re, os
import match_known2 as MK

SCR = "/home/jme/scratch_ptf"
COUNTS = "/home/jme/Downloads/posters-2024plus.biomarkers-counts-v2.csv"
SEEDED = f"{SCR}/deepseek_seeded.jsonl"
OUT = "/home/jme/Downloads/posters-2024plus.none-classified.csv"
AMBIG = f"{SCR}/none_ambiguous.json"

MOL = {"gene","protein","transcript","miRNA","metabolite","mutation","signature","lipid","peptide"}
NONENTITY_KIND = {"physiological": "covariate/measurement", "imaging": "imaging/remote-sensing metric",
                  "microbial": "organism/taxon", "cell": "cell type", "behavioral": "behavioral",
                  "morphological": "morphology", "virus": "organism", "drug": "drug/treatment"}
BIOSENSOR = re.compile(r'(GCaMP|GECI|iGluSnFR|RCaMP|jRGECO|dLight|GRAB|PinkyCaMP|jGCaMP|SnFR|WHaloCaMP|FRCaMP|SCaMP|GABASnFR|Venus-i|biosensor|\bsensor\b|reporter construct|indicator construct|Clade \d+ sensor)', re.I)
GENERIC = re.compile(r'^(SNPs?|DEGs?|gene expression( profiles?| data)?|germline variation|differentially expressed genes|candidate genes?( involved.*)?|transcriptomic data|genetic (diversity|variation)|proteins?|biomarkers?|metabolites?|genes?|mutations?|variants?|total (lipid|protein)|virulence genes?|drug resistance mutations?)$', re.I)

def ckey(s): return MK.charkey(s)

# seeded standard IDs (name -> id/source)
seed_id = {}
if os.path.exists(SEEDED):
    for l in open(SEEDED):
        for b in json.loads(l).get("biomarkers", []):
            sid = b.get("standard_id"); src = b.get("id_source")
            if sid and str(sid).strip() and src and src.lower() != "none":
                for nm in [b.get("seed_name"), b.get("canonical_name")] + (b.get("aliases") or []):
                    if nm and str(nm).strip():
                        seed_id.setdefault(ckey(nm), (str(sid).strip(), src))

KB = MK.load_refs()
a2s, plant_genes = KB["a2s"], KB["plant_genes"]

rows = [r for r in csv.DictReader(open(COUNTS)) if r["match_status"] == "none"]
out_rows = []; ambiguous = []
from collections import Counter
tally = Counter()

for r in rows:
    name = r["canonical"]; kind = r.get("kind", ""); k = ckey(name)
    surfaces = [s.strip() for s in (r.get("surface_forms") or "").split(";") if s.strip()] + [name]
    posters = int(r["posters"]); status = r.get("status", "")
    sid = next((seed_id[ckey(s)] for s in surfaces if ckey(s) in seed_id), None)
    is_gene_db = any(ckey(s) in a2s for s in surfaces)
    is_plant_gene = any(ckey(s) in plant_genes for s in surfaces)

    reason = None; sub = ""; conf = ""
    if BIOSENSOR.search(name):
        reason, sub, conf = "NOT_ENTITY", "biosensor/lab tool", "high"
    elif GENERIC.match(name.strip()):
        reason, sub, conf = "NOT_ENTITY", "generic term", "high"
    elif kind in NONENTITY_KIND:
        reason, sub, conf = "NOT_ENTITY", NONENTITY_KIND[kind], "med"
    elif sid:
        reason, sub, conf = "KNOWN_UNCATALOGUED", f"resolves to {sid[1]}:{sid[0]}", "high"
    elif is_gene_db or is_plant_gene:
        reason, sub, conf = "KNOWN_UNCATALOGUED", "known gene (HGNC/Ensembl), not in a biomarker DB", "med"
    elif kind in MOL:
        reason = "AMBIGUOUS"     # -> LLM adjudication
        ambiguous.append({"canonical": name, "kind": kind, "posters": posters,
                          "status": status, "top_conditions": r.get("top_conditions", ""),
                          "surface_forms": r.get("surface_forms", "")})
    else:  # kind 'other' with no signal
        reason = "AMBIGUOUS"
        ambiguous.append({"canonical": name, "kind": kind, "posters": posters,
                          "status": status, "top_conditions": r.get("top_conditions", ""),
                          "surface_forms": r.get("surface_forms", "")})

    tally[(reason, sub)] += 1
    out_rows.append({**r, "reason_code": reason, "reason_detail": sub, "confidence": conf,
                     "resolved_id": (f"{sid[1]}:{sid[0]}" if sid else ""),
                     "recurs_posters": posters})

with open(OUT, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
    w.writeheader(); w.writerows(out_rows)
json.dump(ambiguous, open(AMBIG, "w"))

print(f"none entities classified: {len(rows)}")
print("\ndeterministic reason codes:")
from collections import Counter as C
byreason = C(r["reason_code"] for r in out_rows)
for reason, n in byreason.most_common():
    print(f"  {reason:20s} {n}")
print(f"\n-> AMBIGUOUS (to LLM adjudication): {len(ambiguous)}  [{AMBIG}]")
print("\nNOT_ENTITY / KNOWN breakdown:")
for (reason, sub), n in tally.most_common():
    if reason != "AMBIGUOUS":
        print(f"  {reason:20s} {sub:45s} {n}")
print(f"\n-> {OUT}")
