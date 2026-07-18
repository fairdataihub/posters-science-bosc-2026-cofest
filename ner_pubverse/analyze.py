#!/usr/bin/env python3
"""
Stage D (analysis): turn cleaned NER entities into the deliverable data.

Produces output/analysis.json with:
  - corpus stats (posters, entities, dedup reduction)
  - top canonical entities per type (Method/Material/Metric/Tool)
  - biomarker ENRICHMENT: entities whose presence is most associated with a poster
    reporting >=1 biomarker (lift vs the corpus base rate), and the reverse (depleted)
  - per-subfield methodology profiles (top methods/tools by biomedical subfield)
  - the fair-ly-accurate cleaning showcase (biggest variant merges)
"""
import json, math
from pathlib import Path
from collections import Counter, defaultdict

OUT = Path(__file__).resolve().parent / "output"
TYPES = ["Method", "Material", "Metric", "Tool"]
MIN_DF_ENRICH = 20      # entity must appear in >=20 posters to be scored for enrichment

# poster section headers / honorifics / pure-structural tokens that the NER tags off
# OCR'd layout text, not real entities. Exact-match (casefold) drop for display.
STOP = {
    "introduction", "methods", "method", "results", "result", "discussion",
    "conclusion", "conclusions", "references", "reference", "background",
    "objective", "objectives", "aim", "aims", "abstract", "summary", "overview",
    "purpose", "findings", "finding", "limitations", "acknowledgements",
    "acknowledgments", "directions", "future directions", "materials and methods",
    "methodology", "contact", "contact information", "dr", "prof", "professor",
    "et al", "fig", "figure", "figures", "table", "tables", "author", "authors",
    "data", "datasets", "dataset", "approach", "approaches", "study", "studies",
    # multilingual poster section headers (Spanish / Portuguese / French)
    "resultados", "introducción", "introduccion", "introdução", "introducao",
    "métodos", "metodos", "conclusión", "conclusión.", "conclusão", "conclusao",
    "conclusiones", "conclusões", "resumen", "resumo", "discusión", "discussão",
    "objetivos", "materiais", "referencias", "referências", "résultats", "méthodes",
    "agradecimientos", "agradecimentos",
}

def is_stop(name: str) -> bool:
    return name.strip().casefold() in STOP


def main():
    posters = [json.loads(l) for l in open(OUT / "poster_entities_clean.ndjson")]
    n = len(posters)
    n_bio = sum(1 for p in posters if p["has_biomarkers"])
    base = n_bio / n

    bio_idx = {i for i, p in enumerate(posters) if p["has_biomarkers"]}

    # entity -> set of poster indices; entity -> total mentions
    ent_docs = defaultdict(set)
    ent_total_mentions = Counter()
    for i, p in enumerate(posters):
        keys = set()
        for e in p["ner_entities_clean"]:
            k = (e["text"], e["type"])
            keys.add(k)
            ent_total_mentions[k] += e["count"]
        for k in keys:
            ent_docs[k].add(i)

    # tier-1 re-fold: FAIRLY keys on exact display forms, so case variants that the
    # semantic map didn't touch (machine learning / Machine Learning) can leak. Fold
    # each (casefold, type) group to its most-frequent display form.
    rep, best = {}, {}
    for (text, t), docs in ent_docs.items():
        g = (text.casefold(), t)
        if len(docs) > best.get(g, -1):
            best[g] = len(docs); rep[g] = text
    md, mm = defaultdict(set), Counter()
    for (text, t), docs in ent_docs.items():
        r = (rep[(text.casefold(), t)], t)
        md[r] |= docs
        mm[r] += ent_total_mentions[(text, t)]
    ent_docs, ent_total_mentions = md, mm
    # positive-poster counts computed from folded doc-sets (no double counting)
    ent_pos = Counter({k: len(docs & bio_idx) for k, docs in ent_docs.items()})

    # top per type by document frequency (structural OCR noise removed for display)
    top_by_type = {}
    for t in TYPES:
        rows = [((c), len(ent_docs[(c, t)]), ent_total_mentions[(c, t)])
                for (c, tt) in ent_docs if tt == t and not is_stop(c)]
        rows.sort(key=lambda r: -r[1])
        top_by_type[t] = [{"name": c, "posters": df, "mentions": m}
                          for c, df, m in rows[:30]]

    # enrichment: lift of P(biomarker | entity) vs base rate
    enrich = []
    for (c, t), docs in ent_docs.items():
        df = len(docs)
        if df < MIN_DF_ENRICH or is_stop(c):
            continue
        pos = ent_pos[(c, t)]
        p_bio_given = pos / df
        lift = p_bio_given / base if base else 0.0
        # Wilson lower bound (95%) to rank robustly, not by noisy small counts
        z = 1.96
        phat = p_bio_given
        denom = 1 + z*z/df
        centre = phat + z*z/(2*df)
        margin = z * math.sqrt((phat*(1-phat) + z*z/(4*df))/df)
        wilson_low = (centre - margin) / denom
        enrich.append({"name": c, "type": t, "posters": df, "bio_posters": pos,
                       "p_bio": round(p_bio_given, 3), "lift": round(lift, 2),
                       "wilson_low": round(wilson_low, 3)})
    enriched = sorted([e for e in enrich if e["lift"] > 1],
                      key=lambda e: (-e["wilson_low"], -e["lift"]))[:35]
    depleted = sorted([e for e in enrich if e["lift"] < 1],
                      key=lambda e: (e["p_bio"], -e["posters"]))[:20]

    # per-subfield methodology profiles
    subfield_docs = defaultdict(lambda: defaultdict(Counter))  # subfield -> type -> Counter(entity)
    subfield_count = Counter()
    for p in posters:
        sf = p.get("subfield") or "Unassigned"
        subfield_count[sf] += 1
        seen = set()
        for e in p["ner_entities_clean"]:
            k = (e["text"], e["type"])
            if k in seen:
                continue
            seen.add(k)
            subfield_docs[sf][e["type"]][e["text"]] += 1
    top_subfields = [sf for sf, _ in subfield_count.most_common(10)]
    subfield_profiles = []
    for sf in top_subfields:
        prof = {"subfield": sf, "posters": subfield_count[sf]}
        for t in ["Method", "Tool", "Material"]:
            prof[t] = [{"name": c, "posters": v}
                       for c, v in subfield_docs[sf][t].most_common(8)]
        subfield_profiles.append(prof)

    # cleaning showcase
    clean_index = json.loads((OUT / "clean_index.json").read_text())
    run_summary = json.loads((OUT / "run_summary.json").read_text())

    analysis = {
        "corpus": {
            "posters": n,
            "posters_biomarker_positive": n_bio,
            "base_rate": round(base, 3),
            "posters_with_entities": run_summary["posters_with_any_entity"],
            "total_mentions": run_summary["total_entity_mentions"],
            "sentences": run_summary["sentences"],
            "runtime_sec": run_summary["runtime_sec"],
            "device": run_summary["device"],
        },
        "dedup": {
            "raw_unique_by_type": clean_index["raw_unique_by_type"],
            "clean_unique_by_type": clean_index["clean_unique_by_type"],
            "reduction_pct": clean_index["reduction_pct"],
            "embedding_model": clean_index["embedding_model"],
            "eps": clean_index["eps"],
        },
        "top_by_type": top_by_type,
        "enriched": enriched,
        "depleted": depleted,
        "subfield_profiles": subfield_profiles,
        "biggest_merges": clean_index["biggest_merges"][:20],
    }
    (OUT / "analysis.json").write_text(json.dumps(analysis, indent=2, ensure_ascii=False))
    print("wrote analysis.json")
    print(f"posters={n} bio+={n_bio} ({base:.1%})  enriched={len(enriched)} depleted={len(depleted)}")
    print("\nTop biomarker-enriched entities (Wilson-ranked):")
    for e in enriched[:15]:
        print(f"  [{e['type']:8}] {e['name'][:40]:40} df={e['posters']:4} "
              f"p_bio={e['p_bio']:.2f} lift={e['lift']:.2f}")


if __name__ == "__main__":
    main()
