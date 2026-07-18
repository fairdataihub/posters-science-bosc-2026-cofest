# posters.science → biomarker discovery (BOSC 2026 / CollaborationFest)

An end-to-end pipeline that mines the [posters.science](https://posters.science)
corpus (31,417 machine-actionable scientific posters) for **biomarkers — including
novel / unseen candidates**, catalogues them with conditions and identifiers, and
flags which are absent from a known biomarker database.

This workflow and project was completed as a part of [BOSC CoFest 2026](https://www.open-bio.org/events/bosc-2026/collaborationfest/).

The design goal throughout: **do not perturb the search for unseen biomarkers.**
No keyword pre-filtering is used to decide what is "about" biomarkers — posters are
scoped by *research field* (a model, not a vocabulary), and biomarkers are pulled
from full text by an LLM asked to include implicated/candidate markers, not just
canonical ones.

## Pipeline at a glance

```
posters-science-export.zip (31,417 posters, DataCite 4.7 NDJSON)
        │
        │  filter to publicationYear >= 2024                         → 11,028 posters
        ▼
[01] classify_fields    paper-to-field (BioM-ELECTRA) → OpenAlex field + [CLS] emb
[02] assign_topics      [CLS] nearest-neighbour vs topic_embeddings → subfield/topic
[03] merge_annotations  fold field/domain/topic into each record; split by domain
        │
        │  keep Health Sciences + Life Sciences domains              → 2,930 posters
        ▼
[04] extract_biomarkers DeepSeek full-text, BROAD prompt (mentioned OR implicated)
[05] enrich_catalogue   DeepSeek re-run: acronym, synonyms, conditions, specimen,
                        role, direction, method, population per biomarker
[06] assemble_catalogue collapse names (char → fairly semantic → alias dict) and
                        match each canonical entity vs the known BiomarkerKB list
                        → exact | partial | none   ('none' = candidate novel)
[07] seeded_pass        DeepSeek re-run seeded with our finds; pulls standard IDs
                        (HGNC/UniProt/CHEBI) + ontology conditions → re-match
[09] extract_conditions DeepSeek conditions for the biomarker-negative posters
[10] condition_frequency corpus-wide condition frequency (cross-conference)
[11] master_record      per-poster join of every layer
[12] rematch_extended   re-match vs BiomarkerKB + MarkerDB + PRGdb (HGNC/Ensembl alias)
[13] classify_none      methodical none-parse: NOT_ENTITY / KNOWN_UNCATALOGUED /
[13b] adjudicate_none      NOVEL_CANDIDATE / UNRESOLVED (deterministic + LLM)
[14] mine_known_uncatalogued  reference-DB coverage-gap audit
```

## Models & data

| Component | What | Where it runs |
|---|---|---|
| [`jimnoneill/paper-to-field`](https://huggingface.co/jimnoneill/paper-to-field) | BioM-ELECTRA-Large, 26 OpenAlex fields + topic NN | local GPU (fp32; Pascal) |
| DeepSeek `deepseek-chat` | full-text biomarker extraction / enrichment | API |
| [`fair-ly-accurate`](https://github.com/fairdataihub/fair-ly-accurate-text-synonyms-for-data-cleaning) | synonym-lustre name normalization (gte-large + HDBSCAN) | local CPU |
| BiomarkerKB (`biomarker_list.csv`) + MarkerDB 2.0 + PRGdb 4.0 | curated biomarker reference sets (match targets) | local |
| HGNC + Ensembl Plants | gene-alias resolvers (normalization only, not match targets) | local |

## Name normalization (the three collapse tiers)

Biomarker surface forms are collapsed to canonical entities in three tiers, so
counts are accurate and novelty is judged per-entity rather than per-string:

1. **Character** — NFKC + casefold + strip punctuation (`IL-6` = `IL6`).
2. **Semantic** — `fair-ly-accurate` synonym-lustre: embed distinct names
   (gte-large), HDBSCAN cluster, with the **acronym/short-token holdout** so
   `IL-6` and `IL-8` never merge.
3. **Alias dictionary** — the acronym ↔ full-name ↔ synonym map that the DeepSeek
   passes emit *is* the controlled vocabulary the holdout deliberately leaves open
   (`IL-6` ↔ `interleukin-6`).

## Outputs

Written to `~/Downloads` (see `.gitignore` — data is not committed):

| File | Contents |
|---|---|
| `posters-2024plus-annotated.ndjson` | all 11,028, each record + `_paper_to_field` |
| `posters-2024plus-biomarkers.*` | the 2,930 biomedical posters + `_deepseek_biomarkers` |
| `posters-2024plus.biomarkers-counts.csv` | one row per canonical biomarker + `match_status` |
| `posters-2024plus.biomarker-catalogue.csv` | long: poster × biomarker × condition, full enrichment |
| `posters-2024plus.biomarkers-index.json` | machine-readable summary + novel (`none`) list |

## Running it

See [`docs/WORKFLOW.md`](docs/WORKFLOW.md) for the full end-to-end runbook
(environment, exact commands, host notes). Scripts in `pipeline/` are numbered by
stage; paths are currently set for the build host (parameterize via the config
block at the top of each). DeepSeek needs `DEEPSEEK_API` in the environment.

## Provenance / reproducibility notes

- The corpus dump and export are transferred out-of-band (too large for git).
- `paper-to-field` runs **fp32** on the GTX 1070 — Pascal fp16 is 1/64 rate.
- Topic-embedding row order is validated (nearest-topic field vs classifier field)
  before topic labels are trusted.
- Every DeepSeek stage is resumable (skips ids already in its output file).

## Team

Posters-are-cool (BOSC 2026 CollaborationFest): Jamey O'Neill, Sujeet Kulkarni,
Hudson Smith, Olaitan Awe, Bhavesh Patel.

## Citation

If you use this software, data, or results derived from it, please cite:

> O'Neill J, Kulkarni S, Smith H, Awe O, Patel B. Potential Novel Biomarker
> Nomination from Recent Conference Posters. Posters-are-cool, BOSC 2026
> CollaborationFest, 2026.
> https://github.com/fairdataihub/posters-science-bosc-2026-cofest

A machine-readable citation is in [CITATION.cff](CITATION.cff).

The posters.science platform is described in: Poster Sharing and Discovery Made
Easy with Posters.science. https://doi.org/10.71707/rk36-9x79

## Funding

This work was supported by The Navigation Fund.
