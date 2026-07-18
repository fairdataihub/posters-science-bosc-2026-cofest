"""Stage 14: mine the KNOWN_UNCATALOGUED bucket from the none-classification.

These are real, resolvable markers absent from the reference biomarker DBs — i.e.
a coverage-gap audit of BiomarkerKB / MarkerDB / PRGdb. Characterizes them by ID
source, kind, and novelty, and extracts the high-value gaps: established markers
recurring across >=2 posters (well-known markers the DBs miss + composite clinical
indices like FIB-4 / ABCD2 / INR that molecular DBs don't catalogue).

Input : ~/Downloads/posters-2024plus.none-classified-final.csv  (stage 13/13b)
Output: ~/Downloads/posters-2024plus.known-uncatalogued-mined.csv
"""
import csv
from collections import Counter

DL = "/home/jme/Downloads"
IN = f"{DL}/posters-2024plus.none-classified-final.csv"
OUT = f"{DL}/posters-2024plus.known-uncatalogued-mined.csv"

rows = [r for r in csv.DictReader(open(IN)) if r["reason_code"] == "KNOWN_UNCATALOGUED"]
print(f"KNOWN_UNCATALOGUED total: {len(rows)}")

def id_source(r):
    rid = r.get("resolved_id", "")
    if rid:
        return rid.split(":")[0]
    d = r.get("reason_detail", "")
    return "LLM-established" if "LLM" in d else d

print("\nby ID source:")
for s, n in Counter(id_source(r) for r in rows).most_common():
    print(f"  {n:4d}  {s}")
print("\nby kind:")
for k, n in Counter(r["kind"] for r in rows).most_common():
    print(f"  {n:4d}  {k}")
print("\nby DeepSeek novelty status:")
for s, n in Counter(r["status"] for r in rows).most_common():
    print(f"  {n:4d}  {s}")

# high-value gaps: established + recurring (>=2 posters)
gaps = [r for r in rows if r["status"] == "established" and int(r["posters"]) >= 2]
gaps.sort(key=lambda r: -int(r["posters"]))
with open(OUT, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["marker", "kind", "posters", "mentions", "resolved_id", "top_conditions", "surface_forms"])
    for r in gaps:
        w.writerow([r["canonical"], r["kind"], r["posters"], r["mentions"],
                    r.get("resolved_id", ""), r.get("top_conditions", ""), r.get("surface_forms", "")])

print(f"\nhigh-value DB gaps (established, >=2 posters): {len(gaps)} -> {OUT}")
for r in gaps[:25]:
    print(f"  {r['posters']:>2}p  {r['canonical'][:30]:31s} {r['kind']:10s} "
          f"{r.get('resolved_id','')[:22]:22s} {(r['top_conditions'] or '')[:28]}")
