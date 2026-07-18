#!/usr/bin/env python3
"""
Stage A/B: run PubVerse NER (Method/Material/Metric/Tool) over the 2,929
biomedical posters — title + descriptions + content sections concatenated.

Outputs (to ./output):
  poster_entities.ndjson  one line per poster: metadata + extracted entities
  entities_raw.tsv        surface\ttype\tdoc_freq\ttotal_count  (input to cleaning)
  run_summary.json        corpus-level counts + timing
"""
import json, re, time, unicodedata, sys
from pathlib import Path
from collections import Counter, defaultdict

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from modeling_pubverse_ner import PubVerseNER, split_sentences

NDJSON = HERE.parent / "data-bosc-cofest" / "2026 BOSC CoFest" / "extracted" / "posters-2024plus-biomarkers.ndjson"
OUT = HERE / "output"; OUT.mkdir(exist_ok=True)

# ── light detokenizer: reverse the NER tokenizer's punctuation spacing ────────
_SP_BEFORE = re.compile(r"\s+([)\]\},.;:%?!])")
_SP_AFTER = re.compile(r"([(\[{])\s+")
_SP_BIND = re.compile(r"\s*([-/+])\s*")          # IL - 6 -> IL-6, LC - MS / MS -> LC-MS/MS
_SP_MULTI = re.compile(r"\s{2,}")

def detok(text: str) -> str:
    t = _SP_BIND.sub(r"\1", text)
    t = _SP_BEFORE.sub(r"\1", t)
    t = _SP_AFTER.sub(r"\1", t)
    t = _SP_MULTI.sub(" ", t).strip()
    return t

def norm_key(text: str) -> str:
    """Tier-1 (character) normalization for grouping: NFKC + casefold + squeeze."""
    t = unicodedata.normalize("NFKC", text).casefold()
    t = re.sub(r"\s+", " ", t).strip()
    return t

# ── build per-poster text ────────────────────────────────────────────────────
def poster_text(pj: dict):
    parts = []
    for t in pj.get("titles", []) or []:
        if t.get("title"): parts.append(t["title"])
    for d in pj.get("descriptions", []) or []:
        if d.get("description"): parts.append(d["description"])
    content = pj.get("content") or {}
    for sec in content.get("sections", []) or []:
        if sec.get("sectionTitle"): parts.append(sec["sectionTitle"])
        if sec.get("sectionContent"): parts.append(sec["sectionContent"])
    return "\n".join(parts)

def pick_device(min_free_gb=3.0):
    """Pick the CUDA device with the most free memory; CPU if none has headroom.
    Stays a good neighbour to other jobs by requiring a modest free margin."""
    import torch
    if not torch.cuda.is_available():
        return "cpu"
    best, best_free = None, 0
    for i in range(torch.cuda.device_count()):
        free, _ = torch.cuda.mem_get_info(i)
        if free > best_free:
            best, best_free = i, free
    if best is None or best_free < min_free_gb * (1024**3):
        return "cpu"
    return f"cuda:{best}"


def main():
    print(f"Loading corpus: {NDJSON}")
    records = []
    with open(NDJSON) as f:
        for line in f:
            r = json.loads(line)
            pj = r.get("posterJson") or {}
            if isinstance(pj, str):
                try: pj = json.loads(pj)
                except Exception:
                    import ast; pj = ast.literal_eval(pj)
            ptf = r.get("_paper_to_field") or {}
            dsb = r.get("_deepseek_biomarkers") or {}
            records.append({
                "id": r.get("id"),
                "doi": pj.get("doi"),
                "title": (pj.get("titles") or [{}])[0].get("title", ""),
                "domain": ptf.get("domain"),
                "field": ptf.get("field"),
                "subfield": ptf.get("subfield"),
                "topic": ptf.get("topic"),
                "has_biomarkers": bool(dsb.get("has_biomarkers")),
                "n_deepseek_biomarkers": len(dsb.get("biomarkers") or []),
                "text": poster_text(pj),
            })
    print(f"  {len(records):,} posters loaded")

    # flatten to sentences with a back-pointer to poster index
    sent_texts, sent_owner = [], []
    for i, rec in enumerate(records):
        for s in split_sentences(rec["text"], max_tokens=180):
            sent_texts.append(s); sent_owner.append(i)
    print(f"  {len(sent_texts):,} sentences to run")

    print("Loading model...")
    import torch
    device = pick_device()
    ner = PubVerseNER.from_pretrained("jimnoneill/pubverse-ner-distilled", device=device)
    print(f"  device: {ner.device}")

    # length-bucketing: sort by (word-count proxy) so each batch pads to ~its own
    # max length instead of the global max — keeps peak memory tiny and is a good
    # neighbour to other jobs sharing the GPU.
    order = sorted(range(len(sent_texts)), key=lambda i: len(sent_texts[i].split()))
    TOKEN_BUDGET = 12000   # batch cost ~= n_sent * max_len_in_batch
    MAX_B = 512

    def batches():
        batch, max_wc = [], 0
        for i in order:
            wc = max(1, len(sent_texts[i].split()))
            nm = max(max_wc, wc)
            if batch and (len(batch) + 1) * nm > TOKEN_BUDGET or len(batch) >= MAX_B:
                yield batch
                batch, max_wc = [], 0
                nm = wc
            batch.append(i); max_wc = nm
        if batch:
            yield batch

    t0 = time.time()
    all_ents = [None] * len(sent_texts)
    done = 0
    for bi in batches():
        chunk = [sent_texts[i] for i in bi]
        try:
            res = ner.extract_batch(chunk, batch_size=len(chunk))
        except torch.cuda.OutOfMemoryError:
            torch.cuda.empty_cache()
            # fall back to CPU for this (rare) oversized batch
            saved = ner.device, ner.model
            ner.device = "cpu"; ner.model = ner.model.to("cpu")
            res = ner.extract_batch(chunk, batch_size=len(chunk))
            ner.device, ner.model = saved[0], saved[1].to(saved[0])
        for k, e in zip(bi, res):
            all_ents[k] = e
        done += len(chunk)
        if done % 20000 < len(chunk) or done == len(sent_texts):
            rate = done / (time.time() - t0)
            print(f"    {done:,}/{len(sent_texts):,}  ({rate:,.0f} sent/s)")
    dt = time.time() - t0
    print(f"  NER done in {dt:.1f}s ({len(sent_texts)/dt:,.0f} sent/s)")

    # aggregate per poster + corpus
    per_poster = [defaultdict(int) for _ in records]     # (clean_surface, type) -> count
    corpus_total = Counter()                              # (norm_key, type) -> total mentions
    corpus_docfreq = Counter()                            # (norm_key, type) -> #posters
    display_form = {}                                     # (norm_key, type) -> most common display surface
    display_votes = defaultdict(Counter)

    for owner, ents in zip(sent_owner, all_ents):
        for e in ents or []:
            surf = detok(e["text"])
            if not surf or len(surf) == 1:               # drop lone punctuation
                continue
            typ = e["type"]
            per_poster[owner][(surf, typ)] += 1
            key = (norm_key(surf), typ)
            corpus_total[key] += 1
            display_votes[key][surf] += 1

    seen_doc = [set() for _ in records]
    for owner in range(len(records)):
        for (surf, typ), cnt in per_poster[owner].items():
            key = (norm_key(surf), typ)
            if key not in seen_doc[owner]:
                corpus_docfreq[key] += 1
                seen_doc[owner].add(key)
    for key, votes in display_votes.items():
        display_form[key] = votes.most_common(1)[0][0]

    # write per-poster ndjson
    pe_path = OUT / "poster_entities.ndjson"
    with open(pe_path, "w") as f:
        for rec, pp in zip(records, per_poster):
            ents = [{"text": s, "type": t, "count": c} for (s, t), c in
                    sorted(pp.items(), key=lambda kv: -kv[1])]
            row = {k: rec[k] for k in ("id","doi","title","domain","field","subfield","topic",
                                       "has_biomarkers","n_deepseek_biomarkers")}
            row["n_ner_entities"] = len(ents)
            row["ner_entities"] = ents
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    # write raw entity table (input for fair-ly-accurate cleaning)
    tsv_path = OUT / "entities_raw.tsv"
    with open(tsv_path, "w") as f:
        f.write("surface\ttype\tdoc_freq\ttotal_count\n")
        for key, tot in corpus_total.most_common():
            nk, typ = key
            f.write(f"{display_form[key]}\t{typ}\t{corpus_docfreq[key]}\t{tot}\n")

    by_type = Counter()
    for (nk, typ), tot in corpus_total.items():
        by_type[typ] += 1
    mentions_by_type = Counter()
    for (nk, typ), tot in corpus_total.items():
        mentions_by_type[typ] += tot

    summary = {
        "posters": len(records),
        "sentences": len(sent_texts),
        "runtime_sec": round(dt, 1),
        "sent_per_sec": round(len(sent_texts) / dt, 1),
        "device": ner.device,
        "total_entity_mentions": int(sum(corpus_total.values())),
        "unique_entities_raw": len(corpus_total),
        "unique_by_type": dict(by_type),
        "mentions_by_type": dict(mentions_by_type),
        "posters_with_any_entity": sum(1 for pp in per_poster if pp),
    }
    with open(OUT / "run_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print("\n=== SUMMARY ===")
    print(json.dumps(summary, indent=2))
    print(f"\nwrote:\n  {pe_path}\n  {tsv_path}\n  {OUT/'run_summary.json'}")

if __name__ == "__main__":
    main()
