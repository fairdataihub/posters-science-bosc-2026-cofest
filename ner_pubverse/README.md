# PubVerse NER × fair-ly-accurate — methodology landscape of the biomarker posters

A complementary read of the 2,929 biomedical posters (Health + Life Sciences, 2024+):
instead of extracting *biomarkers* (the DeepSeek layer), this runs the distilled
scientific-NER model [`jimnoneill/pubverse-ner-distilled`](https://huggingface.co/jimnoneill/pubverse-ner-distilled)
over each poster's **title + descriptions + OCR content** to map the *methodology* —
**Method / Material / Metric / Tool** — then normalizes the pull with
[fair-ly-accurate](https://github.com/fairdataihub/fair-ly-accurate-text-synonyms-for-data-cleaning).

## Pipeline

| Step | Script | Output |
|---|---|---|
| Model + inference wrapper (self-contained, also pushed to the HF repo) | `modeling_pubverse_ner.py` | — |
| Run NER over all posters (GPU, length-bucketed, sentence-segmented) | `run_ner_corpus.py` | `output/poster_entities.ndjson`, `output/entities_raw.tsv`, `output/run_summary.json` |
| Clean with FAIRLY synonym-lustre (gte-large-en-v1.5 → HDBSCAN → most-frequent form, acronym holdout, per entity type) | `clean_entities_fairly.py` | `output/poster_entities_clean.ndjson`, `output/clean_entities.tsv`, `output/clean_index.json`, `output/fairly_review.<Type>.tsv` |
| Analysis: toolkit ranks, biomarker enrichment (lift), tier-1 casefold re-fold, stoplist | `analyze.py` | `output/analysis.json` |
| Self-contained HTML report | `build_artifact.py` | `output/methodology_landscape.html` |

## Headline numbers

- **2,929** posters · **189,055** sentences · **106,032** entity mentions · **725 sent/s** on one GPU
- **45,003 → 34,411** unique entities after cleaning (−23% avg; −20% Tool … −25% Metric)
- **46.7%** of posters report ≥1 biomarker; molecular assays (qPCR, flow cytometry, RNA-seq)
  and clinical measures (ALT, BMI, miRNAs) are ~2× enriched in biomarker-positive posters.

## Notes

- Static (potion) embeddings have no hard context limit, but the IDCNN encoder is
  local and was trained on ≤256-token sentences, so text is sentence-segmented for
  inference (`extract_document` in the modeling module does this generically).
- The acronym/short-token **holdout** protects short forms (`IL-6` ≠ `IL-8`, `PCR`
  stays whole); ε = 0.12 is conservative. Review gates are the `fairly_review.*.tsv`.
- A stoplist drops poster section headers the NER tags off OCR layout (METHODS,
  INTRODUCTION, RESULTADOS, …); see `analyze.py`.

## Reproduce

```bash
python run_ner_corpus.py       # ~4 min on a GPU
python clean_entities_fairly.py
python analyze.py
python build_artifact.py
```
