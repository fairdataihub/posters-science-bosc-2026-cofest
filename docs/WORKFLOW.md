# End-to-end workflow runbook

Every stage, in order, with the exact command and what it produces. Paths reflect
the build host (`/home/jme/scratch_ptf` working dir, `~/Downloads` for inputs and
deliverables). Adjust the config block at the top of each script for another host.

## Environments

| venv | Python | Purpose |
|---|---|---|
| `~/.venvs/torch-pascal` | 3.12 | GPU inference (torch cu126, transformers 4.57) — stages 01, 02, 08 |
| `~/poster-bot/.venv` | 3.12 | CPU: httpx (DeepSeek) + sentence-transformers + `fairly` — stages 04–07 |

GPU is a GTX 1070 (Pascal, sm_61): run models in **fp32** (fp16 is 1/64 rate).
`export DEEPSEEK_API=...` before the DeepSeek stages (store it in a chmod-600 file,
not inline). `HF_HUB_OFFLINE=1` after models are cached.

## Inputs (transferred out-of-band)

- `~/Downloads/posters-science-export.zip` — 31,417 posters, DataCite 4.7 NDJSON.
- `~/Downloads/biomarker_list.csv` — BiomarkerKB export, 8,228 known entities + conditions.
- `~/Downloads/posters.dump` — pgvector DB dump (used by the separate poster-bot chat app).

## Stages

### 01 — classify_fields  (GPU, ~35 min for 11,028)
```bash
HF_HUB_OFFLINE=1 ~/.venvs/torch-pascal/bin/python pipeline/01_classify_fields.py
```
Filters to `publicationYear >= 2024` (11,028), runs `paper-to-field` (title +
description + content, 384-token cap) → `annotations.jsonl` (field, domain, top-3)
+ `cls_embeddings.npy` + `ids.json`.

### 02 — assign_topics  (CPU/GPU, ~1 min)
```bash
~/.venvs/torch-pascal/bin/python pipeline/02_assign_topics.py
```
Fetches the OpenAlex topic hierarchy (4,516 topics), **validates the
topic_embeddings row order** (nearest-topic field vs classifier field; picks the
ordering above the agreement floor), assigns each poster a topic/subfield →
`topic_assign.json`.

### 03 — merge_annotations  (CPU, seconds)
```bash
~/.venvs/torch-pascal/bin/python pipeline/03_merge_annotations.py
```
Folds field/domain/topic into every record; writes `posters-2024plus-annotated.ndjson`,
the Health+Life subset, and `posters-2024plus.manifest.json` (counts by
domain/field/subfield).

### 04 — extract_biomarkers  (DeepSeek API, ~20 min for 2,930)
```bash
~/poster-bot/.venv/bin/python pipeline/04_extract_biomarkers.py
```
Health+Life posters only. Full untruncated text → broad biomarker list
(`kind/status/role/evidence`) → `deepseek_biomarkers.jsonl`. ~47% carry ≥1 biomarker.

### 05 — enrich_catalogue  (DeepSeek API, ~20 min for 1,368)
```bash
~/poster-bot/.venv/bin/python pipeline/05_enrich_catalogue.py
```
Re-runs the biomarker-positive posters for the rich per-marker record (acronym,
synonyms, conditions, specimen, role, direction, method, population) + poster
metadata/year → `deepseek_catalogue.jsonl`.

### 06 — assemble_catalogue  (CPU, ~10 min; embedding is the slow leg)
```bash
HF_HUB_OFFLINE=1 ~/poster-bot/.venv/bin/python pipeline/06_assemble_catalogue.py
```
Collapses names across the three tiers (char → fairly semantic → alias dict),
matches each canonical entity vs BiomarkerKB (`lib/match_known.py`) →
`biomarkers-counts.csv` + `biomarker-catalogue.csv` + `biomarkers-index.json`.

### 07 — seeded_pass  (DeepSeek API, ~20 min)
```bash
~/poster-bot/.venv/bin/python pipeline/07_seeded_pass.py
```
Full text seeded with our finds + their match status; pulls standard IDs
(HGNC/UniProt/CHEBI/Entrez) + ontology-tagged conditions, focusing on the `none`
(candidate-novel) set → `deepseek_seeded.jsonl`. Re-match with these IDs to split
genuinely-novel from named-differently.

### 09-14 — conditions, frequency, master join, extended re-match, none-classification, gap mining
```bash
~/poster-bot/.venv/bin/python pipeline/09_extract_conditions.py
~/poster-bot/.venv/bin/python pipeline/10_condition_frequency.py
~/poster-bot/.venv/bin/python pipeline/12_rematch_extended.py     # BiomarkerKB+MarkerDB+PRGdb
~/poster-bot/.venv/bin/python pipeline/13_classify_none.py         # deterministic cascade
DEEPSEEK_API=... ~/poster-bot/.venv/bin/python pipeline/13b_adjudicate_none.py
~/poster-bot/.venv/bin/python pipeline/14_mine_known_uncatalogued.py
~/poster-bot/.venv/bin/python pipeline/11_master_record.py         # per-poster join
```

## Notes

- DeepSeek stages are **resumable** — re-running skips ids already in the output.
- DeepSeek and GPU stages are independent workloads and can run concurrently.
- Known-DB matching is heuristic for `partial`; `exact` and `none` are reliable.
  The seeded pass (07) exists to make `none` trustworthy via standard identifiers.
