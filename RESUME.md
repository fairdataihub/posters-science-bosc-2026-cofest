# Resume notes — biomarker pipeline

State: pipeline runs end-to-end. All artifacts on disk.

## Headline result

From the posters.science 2024+ subset (11,028 posters → 2,929 biomedical →
1,368 with biomarkers → 7,394 biomarker records → 3,430 canonical entities):

**"none" (unmatched vs BiomarkerKB + MarkerDB + PRGdb, HGNC/Ensembl-normalized,
seeded standard-IDs) methodically parsed into reason codes:**

| reason_code | count | |
|---|---|---|
| NOT_ENTITY | 1,349 (68%) | covariates, organisms, imaging, methods, generic |
| KNOWN_UNCATALOGUED | 466 (24%) | real established markers absent from our DBs |
| **NOVEL_CANDIDATE** | **116 (6%)** | **defensible novel pool** (across 81 posters) |
| UNRESOLVED | 40 (2%) | human-review queue |

Match distribution of the 3,430 canonical: exact 727 / partial 732 / none 1,971.

## Deliverables (in ~/Downloads)

| File | What |
|---|---|
| `posters-2024plus-master.ndjson` | 11,028 posters, all layers joined (class+biomarkers+match+reason+conditions) |
| `posters-2024plus.novel-candidates-final.csv` | the 116 NOVEL_CANDIDATE |
| `posters-2024plus.none-classified-final.csv` | all 1,971 none with reason_code + LLM notes |
| `posters-2024plus.biomarkers-counts-v2.csv` | 3,430 canonical + match_status + match_source |
| `posters-2024plus.biomarker-catalogue.csv` | long: poster × biomarker × condition (8,819 rows) |
| `posters-2024plus.condition-frequency.csv` | 2,382 conditions across 1,884 posters |
| `posters-2024plus.biomarkers.zip` | shippable biomarker dataset + README |

## Reference DBs (pipeline/lib/fetch_refdbs.sh pulls these)

BiomarkerKB (`biomarker_list.csv`, out-of-band) · MarkerDB 2.0 (protein/chemical/
variant) · PRGdb 4.0 reference R-genes · HGNC (gene alias) · Ensembl Plants
(crop/model gene alias). `refdb/` in ~/scratch_ptf.

## OPEN / NEXT

1. **KNOWN_UNCATALOGUED (466)** — mined (stage 14); 26 established DB-gap markers surfaced.
3. **Broad plant alias table** (full Ensembl Plants / Gramene) — TODO for non-R-gene plant candidates (AVR-Pii, Cry1Ab, SR45). Flagged in fetch_refdbs.sh.
4. **Condition normalization** — many top conditions show "NOT in known DB" only due to name-vs-DOID mismatch; normalize condition strings to DOID/MONDO for cleaner frequency.
5. **Push repo to GitHub** — committed locally; needs auth:
   `gh auth login && git -C ~/posters-science-bosc-2026-cofest push -u origin main`

## Env / gotchas

- DeepSeek key: `DEEPSEEK_API` env var. GPU is Pascal → fp32 only. Run scripts with
  `python -u` + ABSOLUTE paths (tool shell resets cwd; buffered stdout hides progress).
- Working scripts: `~/scratch_ptf/`. Staged copies: repo `pipeline/` (01–13b + lib/).
