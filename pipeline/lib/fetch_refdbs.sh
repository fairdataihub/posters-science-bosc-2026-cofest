#!/usr/bin/env bash
# Download the curated biomarker reference sets used by the extended matcher.
# HGNC is used ONLY as a gene-alias resolver (not a match target).
set -euo pipefail
OUT="${1:-$HOME/scratch_ptf/refdb}"; mkdir -p "$OUT"; cd "$OUT"
# MarkerDB 2.0 (markerdb.ca) — curated molecular biomarkers + conditions
curl -sL "https://markerdb.ca/pages/download_all_proteins?format=tsv"          -o markerdb_proteins.tsv
curl -sL "https://markerdb.ca/pages/download_all_chemicals?format=tsv"         -o markerdb_chemicals.tsv
curl -sL "https://markerdb.ca/pages/download_all_sequence_variants?format=tsv" -o markerdb_sequence_variants.tsv
# HGNC complete set (gene symbol + alias/prev symbols) — alias resolution only
curl -sL "https://storage.googleapis.com/public-download-files/hgnc/tsv/tsv/hgnc_complete_set.txt" -o hgnc_complete_set.txt
# PRGdb 4.0 curated REFERENCE plant resistance genes (152; NOT the putative set)
curl -sL "http://prgdb.org/prgdb4/ReferenceResistanceGenes.fasta.gz" -o prgdb_reference.fasta.gz
gunzip -kf prgdb_reference.fasta.gz
# BiomarkerKB (biomarker_list.csv) is transferred out-of-band into ~/Downloads.
# TODO (follow-up): broad plant gene-alias table (Ensembl Plants / Gramene) for
# non-R-gene plant candidates (effectors, Bt toxins, e.g. AVR-Pii, Cry1Ab, SR45).
echo "refdb ready in $OUT"
