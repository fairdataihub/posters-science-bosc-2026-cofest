#!/usr/bin/env python3
"""
Stage C: clean & polish the raw NER pull with fair-ly-accurate (FAIRLY).

Three-tier collapse, per the pipeline README:
  1. Character  — already applied upstream (NFKC + casefold + detok) when the raw
                  table was built.
  2. Semantic   — FAIRLY synonym-lustre: embed distinct surfaces (gte-large-en-v1.5)
                  -> HDBSCAN -> map each cluster to its most-frequent member, with
                  the acronym / short-token HOLDOUT so IL-6 and IL-8 never merge.
  3. (alias dict) left open by the holdout — not needed for these 4 entity types.

Clustering is done independently per entity type (Method / Material / Metric / Tool)
so a Method never merges with a Tool of the same surface form.

Outputs (./output):
  fairly_review.<Type>.tsv     human-review gate: canonical, freq, merged variants
  clean_entities.tsv           canonical, type, doc_freq, total_count, n_variants, variants
  poster_entities_clean.ndjson per-poster entities mapped to canonical forms
  clean_index.json             before/after stats + top entities per type
"""
import json, sys, os
from pathlib import Path
from collections import Counter, defaultdict

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"
FAIRLY_SRC = Path.home() / "fair-ly-accurate-text-synonyms-for-data-cleaning" / "src"
sys.path.insert(0, str(FAIRLY_SRC))

from fairly import FieldConfig, Normalizer   # noqa: E402

TYPES = ["Method", "Material", "Metric", "Tool"]
EMB_MODEL = "Alibaba-NLP/gte-large-en-v1.5"   # FAIRLY default; cached locally
EPS = 0.12                                     # conservative (subject preset uses 0.10)
CACHE = str(OUT / ".fairly_cache")


def pick_st_device(min_free_gb=3.0):
    try:
        import torch
        if not torch.cuda.is_available():
            return "cpu"
        best, best_free = None, 0
        for i in range(torch.cuda.device_count()):
            free, _ = torch.cuda.mem_get_info(i)
            if free > best_free:
                best, best_free = i, free
        return f"cuda:{best}" if best_free >= min_free_gb * (1024**3) else "cpu"
    except Exception:
        return "cpu"


def embed_terms(terms, device):
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(EMB_MODEL, trust_remote_code=True, device=device)
    return model.encode(list(terms), convert_to_numpy=True, normalize_embeddings=True,
                        batch_size=128, show_progress_bar=False)


def main():
    raw = OUT / "entities_raw.tsv"
    # load raw entities per type: surface -> total_count (and doc_freq)
    by_type_counts = {t: {} for t in TYPES}
    with open(raw) as f:
        next(f)  # header
        for line in f:
            surface, typ, doc_freq, total = line.rstrip("\n").split("\t")
            if typ in by_type_counts:
                by_type_counts[typ][surface] = int(total)
    for t in TYPES:
        print(f"  {t:9}: {len(by_type_counts[t]):>6,} distinct raw surfaces")

    device = pick_st_device()
    print(f"embedding device: {device}")

    # build a synonym map per type
    smaps = {}
    for t in TYPES:
        counts = by_type_counts[t]
        if len(counts) < 2:
            smaps[t] = None
            continue
        terms = list(counts.keys())
        emb = embed_terms(terms, device)
        cfg = FieldConfig(name=t, strategy="semantic", eps=EPS, holdout=True,
                          authority=None, min_cluster_size=2, min_samples=1,
                          cluster_method="leaf", embedding_model=EMB_MODEL)
        smap = Normalizer(cfg, cache_dir=CACHE).build(counts, emb=emb)
        smaps[t] = smap
        smap.write_review(str(OUT / f"fairly_review.{t}.tsv"), counts=counts)
        print(f"  {t:9}: {len(smap):>6,} variants merged into "
              f"{smap.meta['n_clusters']:,} clusters "
              f"(held out {smap.meta['n_held_out']:,})")

    def canon(surface, typ):
        sm = smaps.get(typ)
        return sm.apply(surface) if sm is not None else surface

    # recompute canonical doc_freq / total_count from per-poster data (accurate)
    canon_docfreq = Counter()
    canon_total = Counter()
    canon_variants = defaultdict(set)
    pe_in = OUT / "poster_entities.ndjson"
    pe_out = OUT / "poster_entities_clean.ndjson"
    with open(pe_in) as f, open(pe_out, "w") as g:
        for line in f:
            row = json.loads(line)
            seen = set()
            merged = defaultdict(int)
            for e in row.get("ner_entities", []):
                c = canon(e["text"], e["type"])
                key = (c, e["type"])
                merged[key] += e["count"]
                canon_total[key] += e["count"]
                canon_variants[key].add(e["text"])
                if key not in seen:
                    canon_docfreq[key] += 1
                    seen.add(key)
            row["ner_entities_clean"] = [
                {"text": c, "type": t, "count": n}
                for (c, t), n in sorted(merged.items(), key=lambda kv: -kv[1])
            ]
            row["n_ner_entities_clean"] = len(row["ner_entities_clean"])
            del row["ner_entities"]
            g.write(json.dumps(row, ensure_ascii=False) + "\n")

    # write cleaned catalogue
    with open(OUT / "clean_entities.tsv", "w") as f:
        f.write("canonical\ttype\tdoc_freq\ttotal_count\tn_variants\tvariants\n")
        for (c, t), df in sorted(canon_docfreq.items(), key=lambda kv: -kv[1]):
            variants = sorted(canon_variants[(c, t)], key=lambda v: v.lower())
            f.write(f"{c}\t{t}\t{df}\t{canon_total[(c,t)]}\t{len(variants)}\t"
                    f"{' | '.join(v for v in variants if v != c)}\n")

    # index / summary
    raw_unique = {t: len(by_type_counts[t]) for t in TYPES}
    clean_unique = Counter(t for (_, t) in canon_docfreq)
    top = {}
    for t in TYPES:
        rows = [((c), canon_docfreq[(c, t)], canon_total[(c, t)])
                for (c, tt) in canon_docfreq if tt == t]
        rows.sort(key=lambda r: -r[1])
        top[t] = [{"name": c, "doc_freq": df, "mentions": tot} for c, df, tot in rows[:25]]
    biggest_merges = []
    for (c, t), vs in canon_variants.items():
        if len(vs) > 1:
            biggest_merges.append({"canonical": c, "type": t, "n_variants": len(vs),
                                   "doc_freq": canon_docfreq[(c, t)],
                                   "variants": sorted(vs, key=lambda v: v.lower())})
    biggest_merges.sort(key=lambda m: -m["n_variants"])

    index = {
        "embedding_model": EMB_MODEL, "eps": EPS,
        "raw_unique_by_type": raw_unique,
        "clean_unique_by_type": dict(clean_unique),
        "reduction_pct": {t: round(100 * (1 - clean_unique[t] / max(1, raw_unique[t])), 1)
                          for t in TYPES},
        "top_by_type": top,
        "biggest_merges": biggest_merges[:40],
    }
    with open(OUT / "clean_index.json", "w") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)

    print("\n=== CLEAN SUMMARY ===")
    for t in TYPES:
        print(f"  {t:9}: {raw_unique[t]:>6,} -> {clean_unique[t]:>6,} "
              f"(-{index['reduction_pct'][t]}%)")
    print(f"\nwrote clean_entities.tsv, poster_entities_clean.ndjson, clean_index.json, "
          f"fairly_review.*.tsv")


if __name__ == "__main__":
    main()
