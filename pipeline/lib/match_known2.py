"""Extended known-biomarker matcher: BiomarkerKB + MarkerDB (protein/chemical/
variant) as CURATED match targets, with HGNC used only as a gene-alias resolver
(PD-L1 -> CD274) applied to BOTH our names and the reference names. HGNC is NOT a
match target — being a real gene != being a known biomarker.
"""
import csv, re, unicodedata
from collections import defaultdict

REF = "/home/jme/scratch_ptf/refdb"
BIOMARKERKB = "/home/jme/Downloads/biomarker_list.csv"

def charkey(s):
    s = unicodedata.normalize("NFKC", str(s)).casefold().strip()
    return re.sub(r"[\s\-_/]+", "", s)
_TOK = re.compile(r"[a-z0-9]+")
def tokens(s):
    return set(_TOK.findall(unicodedata.normalize("NFKC", str(s)).casefold()))
STOP = {"protein","proteins","gene","genes","cell","cells","cellular","factor","factors",
    "receptor","receptors","acid","acids","marker","markers","level","levels","ratio","index",
    "score","count","counts","activity","expression","dna","rna","mrna","signaling","signalling",
    "pathway","disease","diseases","syndrome","disorder","novel","candidate","potential","putative",
    "some","totally","the","and","of","in","type","subunit","alpha","beta","gamma","chain","human",
    "total","serum","plasma","blood","concentration","status","profile","signature","response","function"}

def _split(v):
    return [x for x in re.split(r"[|;,]", v or "") if x.strip()]

def load_hgnc():
    """charkey(alias/prev/symbol) -> official symbol. HGNC (human) + Ensembl Plants
    (crop/model species) as ALIAS RESOLVERS only — not match targets."""
    a2s = {}
    plant_genes = set()   # charkey of every known plant gene symbol/synonym (a signal, not a match)
    import os as _os
    with open(f"{REF}/hgnc_complete_set.txt") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            sym = (row.get("symbol") or "").strip()
            if not sym:
                continue
            a2s[charkey(sym)] = sym
            for field in ("alias_symbol", "prev_symbol"):
                for a in _split(row.get(field)):
                    a2s.setdefault(charkey(a), sym)
    # Ensembl Plants: col0 = gene symbol, col1 = synonym (blank ok)
    pfile = f"{REF}/ensembl_plants_aliases.tsv"
    if _os.path.exists(pfile):
        for line in open(pfile):
            parts = line.rstrip("\n").split("\t")
            sym = (parts[0] or "").strip() if parts else ""
            syn = (parts[1].strip() if len(parts) > 1 else "")
            if sym:
                a2s.setdefault(charkey(sym), sym)
                plant_genes.add(charkey(sym))
            if syn:
                a2s.setdefault(charkey(syn), sym or syn)
                plant_genes.add(charkey(syn))
    return a2s, plant_genes

def load_refs():
    a2s, plant_genes = load_hgnc()
    def norm(name):
        k = charkey(name)
        s = a2s.get(k)
        return charkey(s) if s else k       # gene alias -> official symbol key

    known = {}          # normalized key -> {"display","source","conditions":set}
    tok_index = defaultdict(set)
    def add(name, source, conditions):
        k = norm(name)
        if not k:
            return
        e = known.setdefault(k, {"display": name, "source": source, "conditions": set()})
        for c in conditions:
            if c: e["conditions"].add(c)
        for t in tokens(name):
            if t not in STOP and len(t) >= 3:
                tok_index[t].add(k)

    # BiomarkerKB
    for row in csv.DictReader(open(BIOMARKERKB)):
        e = (row.get("assessed_biomarker_entity") or "").strip()
        if e:
            add(e, "BiomarkerKB", [ (row.get("condition") or "").strip() ])
    # MarkerDB proteins (name + gene_name)
    for row in csv.DictReader(open(f"{REF}/markerdb_proteins.tsv"), delimiter="\t"):
        conds = _split(row.get("conditions"))
        for nm in (row.get("name"), row.get("gene_name")):
            if nm and nm.strip():
                add(nm.strip(), "MarkerDB-protein", conds)
    # MarkerDB chemicals (name)
    for row in csv.DictReader(open(f"{REF}/markerdb_chemicals.tsv"), delimiter="\t"):
        if (row.get("name") or "").strip():
            add(row["name"].strip(), "MarkerDB-chemical", _split(row.get("conditions")))
    # MarkerDB sequence variants (gene_symbol)
    for row in csv.DictReader(open(f"{REF}/markerdb_sequence_variants.tsv"), delimiter="\t"):
        if (row.get("gene_symbol") or "").strip():
            add(row["gene_symbol"].strip(), "MarkerDB-variant", _split(row.get("conditions")))
    # PRGdb 4.0 curated REFERENCE plant resistance genes (152; NOT the putative set).
    # FASTA headers look like ">129_Asc-1" -> gene name after the first underscore.
    import os as _os
    prg = f"{REF}/prgdb_reference.fasta"
    if _os.path.exists(prg):
        for line in open(prg):
            if line.startswith(">"):
                nm = line[1:].strip().split("_", 1)[-1]
                if nm:
                    add(nm, "PRGdb-Rgene", ["plant disease resistance"])

    return {"known": known, "tok_index": tok_index, "a2s": a2s, "norm": norm,
            "plant_genes": plant_genes}

def classify(surface_forms, KB):
    norm = KB["norm"]
    keys = [norm(s) for s in surface_forms if s and str(s).strip()]
    keys = [k for k in keys if k]
    # exact
    for k in keys:
        if k in KB["known"]:
            e = KB["known"][k]
            return "exact", e["display"], e["source"], sorted(e["conditions"])[:5]
    # partial: >=50% of OUR non-generic tokens shared with a known entity
    for sf in surface_forms:
        our = {t for t in tokens(sf) if t not in STOP and len(t) >= 3}
        if not our:
            continue
        cand = set()
        for t in our:
            cand |= KB["tok_index"].get(t, set())
        for kk in cand:
            their = {t for t in tokens(KB["known"][kk]["display"]) if t not in STOP and len(t) >= 3}
            if their and len(our & their) / len(our) >= 0.5:
                e = KB["known"][kk]
                return "partial", e["display"], e["source"], sorted(e["conditions"])[:5]
    return "none", None, None, []

if __name__ == "__main__":
    KB = load_refs()
    print(f"known biomarker keys (BiomarkerKB + MarkerDB, HGNC-normalized): {len(KB['known'])}")
    for t in [["PD-L1"],["PDL1"],["GLP-1"],["HBsAg"],["HBV DNA"],["CD11c"],["troponin"],
              ["bindin"],["EBR1"],["Type 2 deiodinase"],["LINC00958"],["NDVI"],["BMI"]]:
        st, disp, src, cond = classify(t, KB)
        print(f"  {str(t):24s} -> {st:8s} {src or '':18s} {disp or ''}")
