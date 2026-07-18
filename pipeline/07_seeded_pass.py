"""Seeded DeepSeek pass: full text AGAIN, seeded with the biomarkers we already
extracted + their match status against the known DB. For each biomarker (and
especially the unmatched 'none' candidates) pull a STANDARD IDENTIFIER
(HGNC/UniProt/CHEBI/Entrez/Ensembl) + official name + normalized condition
(DOID/MONDO). Lets us re-match and separate truly-novel from naming-mismatch.

Run after assemble_catalogue.py. Resumable, concurrent, full untruncated text.
Run: DEEPSEEK_API=... ~/poster-bot/.venv/bin/python seeded_pass.py
"""
import os, json, glob, csv, asyncio, httpx

SCR = "/home/jme/scratch_ptf"
SRC = "/home/jme/Downloads/posters-export"
CAT = f"{SCR}/deepseek_catalogue.jsonl"
COUNTS = "/home/jme/Downloads/posters-2024plus.biomarkers-counts.csv"
OUT = f"{SCR}/deepseek_seeded.jsonl"
KEY = os.environ["DEEPSEEK_API"]
CONC = 8
MODEL = "deepseek-chat"

# canonical -> match_status from the assembled counts
canon_match = {}
if os.path.exists(COUNTS):
    for row in csv.DictReader(open(COUNTS)):
        canon_match[row["canonical"]] = row["match_status"]

cat = {json.loads(l)["id"]: json.loads(l) for l in open(CAT)}

def text_of(pj):
    ts = pj.get("titles") or []
    title = ts[0].get("title","") if ts else ""
    desc = " ".join((d.get("description","") or "") for d in (pj.get("descriptions") or []))
    c = pj.get("content")
    content = c if isinstance(c,str) else (json.dumps(c) if c else "")
    return f"{title}\n\n{desc}\n\n{content}".strip()

records = {}
for fp in sorted(glob.glob(f"{SRC}/*.ndjson")):
    for ln in open(fp):
        if not ln.strip(): continue
        d = json.loads(ln); rid = str(d["id"])
        if rid not in cat: continue
        pj = d["posterJson"]
        if isinstance(pj, str): pj = json.loads(pj)
        records[rid] = {"text": text_of(pj)}

done = set()
if os.path.exists(OUT):
    done = {json.loads(l)["id"] for l in open(OUT)}
todo = [rid for rid in cat if rid not in done]
print(f"posters to re-seed: {len(todo)} (of {len(cat)}) | match statuses loaded: {len(canon_match)}", flush=True)

SYS = (
 "You are refining a biomarker catalogue. You are given a scientific poster's full text AND a "
 "SEED list of biomarkers already extracted from it, each tagged with our match status against a "
 "known biomarker database (exact | partial | none). For EVERY seed biomarker, return an enriched "
 "record. Put special effort into the 'none' ones: supply a STANDARD IDENTIFIER so they can be "
 "re-checked. Use ONLY the text + your biomedical knowledge of standard nomenclature; never invent "
 "an identifier you are not confident about (use null instead). Also add any biomarkers the seed missed.\n"
 "Return STRICT JSON: {\"biomarkers\": [{"
 "\"seed_name\": \"the seed name you are enriching (or 'NEW' if newly found)\", "
 "\"canonical_name\": \"official/standard name\", "
 "\"standard_id\": \"HGNC symbol | UniProt acc | CHEBI id | Entrez id | Ensembl id | null\", "
 "\"id_source\": \"HGNC|UniProt|CHEBI|Entrez|Ensembl|none\", "
 "\"aliases\": [\"all names/acronyms/synonyms\"], "
 "\"kind\": \"gene|protein|transcript|miRNA|metabolite|lipid|mutation|signature|imaging|physiological|cell|microbial|other\", "
 "\"conditions\": [{\"name\": \"disease\", \"ontology_id\": \"DOID/MONDO id or null\"}], "
 "\"specimen\": \"or null\", \"role\": \"diagnostic|prognostic|predictive|risk|exposure|monitoring|response|safety|unspecified\", "
 "\"direction\": \"increased|decreased|altered|present|absent|unspecified\", "
 "\"confidence\": \"high|medium|low\", "
 "\"note\": \"<=20 words: correction or why still likely novel\"}]}."
)

sem = asyncio.Semaphore(CONC)
out_f = open(OUT, "a"); lock = asyncio.Lock(); n = [0]

def seed_for(rid):
    seeds = []
    for b in cat[rid].get("biomarkers", []):
        nm = (b.get("name") or "").strip()
        if not nm: continue
        seeds.append({"name": nm, "acronym": b.get("acronym"),
                      "synonyms": b.get("synonyms"), "kind": b.get("kind"),
                      "match_status": canon_match.get(nm, "unknown")})
    return seeds

async def one(client, rid):
    async with sem:
        seeds = seed_for(rid)
        user = (f"POSTER TEXT:\n{records[rid]['text'][:55000]}\n\n"
                f"SEED BIOMARKERS (enrich each; focus on match_status='none'):\n"
                f"{json.dumps(seeds, ensure_ascii=False)}")
        payload = {"model": MODEL, "temperature": 0,
                   "response_format": {"type": "json_object"},
                   "messages": [{"role": "system", "content": SYS},
                                {"role": "user", "content": user}]}
        for attempt in range(4):
            try:
                r = await client.post("https://api.deepseek.com/chat/completions",
                                      headers={"Authorization": f"Bearer {KEY}"},
                                      json=payload, timeout=240)
                if r.status_code == 200:
                    data = json.loads(r.json()["choices"][0]["message"]["content"])
                    async with lock:
                        out_f.write(json.dumps({"id": rid, "biomarkers": data.get("biomarkers", [])},
                                               ensure_ascii=False) + "\n"); out_f.flush()
                        n[0] += 1
                        if n[0] % 50 == 0:
                            print(f"  {n[0]}/{len(todo)}", flush=True)
                    return
                if r.status_code in (429, 500, 502, 503):
                    await asyncio.sleep(2*(attempt+1)); continue
                print(f"  {rid}: HTTP {r.status_code} {r.text[:100]}", flush=True); return
            except Exception:
                await asyncio.sleep(2*(attempt+1))
        print(f"  {rid}: failed", flush=True)

async def main():
    async with httpx.AsyncClient() as client:
        await asyncio.gather(*[one(client, rid) for rid in todo])
    print(f"done: {n[0]} posters -> {OUT}", flush=True)

asyncio.run(main())
