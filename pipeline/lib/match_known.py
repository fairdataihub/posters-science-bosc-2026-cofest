"""Match a biomarker (by any of its surface forms) against the known BiomarkerKB
list -> exact | partial | none. 'none' is the goal: a candidate novel marker.
"""
import csv, re, unicodedata
from functools import lru_cache

KNOWN_CSV = "/home/jme/Downloads/biomarker_list.csv"

def charkey(s):
    s = unicodedata.normalize("NFKC", str(s)).casefold().strip()
    return re.sub(r"[\s\-_/]+", "", s)

_TOKEN = re.compile(r"[a-z0-9]+")
def tokens(s):
    return set(_TOKEN.findall(unicodedata.normalize("NFKC", str(s)).casefold()))

# generic biomedical / english words that must never, alone, drive a partial match
STOP = {
    "protein", "proteins", "gene", "genes", "cell", "cells", "cellular", "factor",
    "factors", "receptor", "receptors", "acid", "acids", "marker", "markers",
    "level", "levels", "ratio", "index", "score", "count", "counts", "activity",
    "expression", "dna", "rna", "mrna", "signaling", "signalling", "pathway",
    "disease", "diseases", "syndrome", "disorder", "novel", "candidate", "potential",
    "putative", "some", "totally", "the", "and", "of", "in", "type", "subunit",
    "alpha", "beta", "gamma", "chain", "human", "total", "serum", "plasma", "blood",
    "concentration", "status", "profile", "signature", "response", "function",
}

def load_known():
    exact = {}          # charkey -> canonical known entity
    known_tokens = {}   # charkey -> token set
    conditions = {}     # charkey(entity) -> set(conditions)
    with open(KNOWN_CSV) as f:
        for row in csv.DictReader(f):
            e = (row.get("assessed_biomarker_entity") or "").strip()
            if not e:
                continue
            k = charkey(e)
            if not k:
                continue
            exact.setdefault(k, e)
            known_tokens.setdefault(k, tokens(e))
            c = (row.get("condition") or "").strip()
            if c:
                conditions.setdefault(k, set()).add(c)
    # index tokens -> keys for partial lookup (only meaningful tokens, len>=3)
    tok_index = {}
    for k, tks in known_tokens.items():
        for t in tks:
            if len(t) >= 3:
                tok_index.setdefault(t, set()).add(k)
    return {"exact": exact, "known_tokens": known_tokens,
            "tok_index": tok_index, "conditions": conditions}

def classify(surface_forms, KB):
    """surface_forms: list of names/acronyms/synonyms for ONE of our biomarkers.
    Returns (status, matched_known_entity_or_None, matched_conditions)."""
    keys = [charkey(s) for s in surface_forms if s and charkey(s)]
    # 1) exact on any surface form
    for k in keys:
        if k in KB["exact"]:
            return "exact", KB["exact"][k], sorted(KB["conditions"].get(k, []))[:5]
    # 2) partial: meaningful-token coverage (>=50% of OUR non-generic tokens are
    #    shared with a known entity). Generic biomedical words never drive a match.
    best = None
    for sf in surface_forms:
        our = {t for t in tokens(sf) if t not in STOP and len(t) >= 3}
        if not our:
            continue
        cand = set()
        for t in our:
            cand |= KB["tok_index"].get(t, set())
        for kk in cand:
            their = {t for t in KB["known_tokens"][kk] if t not in STOP and len(t) >= 3}
            if not their:
                continue
            shared = our & their
            if len(shared) / len(our) >= 0.5:
                best = kk; break
        if best:
            break
    if best:
        return "partial", KB["exact"][best], sorted(KB["conditions"].get(best, []))[:5]
    return "none", None, []

if __name__ == "__main__":
    KB = load_known()
    print(f"known entities indexed: {len(KB['exact'])}")
    tests = [
        ["BRCA1"], ["brca1"], ["IL-6", "interleukin-6"], ["PD-L1", "PDL1"],
        ["CA-125"], ["troponin"], ["ATM"],
        ["LINC00958"], ["inertial sensor movement data"],
        ["some totally novel candidate protein XYZ-9000"], ["NDVI"],
    ]
    for t in tests:
        status, ent, conds = classify(t, KB)
        print(f"  {str(t):45s} -> {status:8s} {ent or ''}  {('| '+', '.join(conds[:2])) if conds else ''}")
