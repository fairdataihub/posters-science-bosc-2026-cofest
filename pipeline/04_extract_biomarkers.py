"""Broad biomarker extraction over the field-relevant (Health+Life) posters via
DeepSeek. Sends FULL untruncated poster text; asks for every biomarker mentioned
OR implicated, interpreted broadly (novel/candidate/putative included), not just
canonical named markers. Async, rate-limited, resumable.

Run: DEEPSEEK_API=... ~/poster-bot/.venv/bin/python deepseek_biomarkers.py
"""
import os, json, glob, asyncio, httpx

SCR = "/home/jme/scratch_ptf"
SRC = "/home/jme/Downloads/posters-export"
OUT = f"{SCR}/deepseek_biomarkers.jsonl"
KEY = os.environ["DEEPSEEK_API"]
CONC = 8
MODEL = "deepseek-chat"

# relevant domains = Health + Life Sciences (10 biomedical fields)
F2D = {t["field_id"]: t["domain"] for t in json.load(open(f"{SCR}/openalex_topics.json"))}
REL = {"Health Sciences", "Life Sciences"}
relevant_ids = {json.loads(l)["id"] for l in open(f"{SCR}/annotations.jsonl")
                if F2D[json.loads(l)["field_id"]] in REL}

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
        if rid not in relevant_ids: continue
        pj = d["posterJson"]
        if isinstance(pj, str): pj = json.loads(pj)
        records[rid] = {"doi": pj.get("doi"), "text": text_of(pj)}

done = set()
if os.path.exists(OUT):
    done = {json.loads(l)["id"] for l in open(OUT)}
todo = [(rid, r) for rid, r in records.items() if rid not in done]
print(f"relevant posters: {len(records)} | already done: {len(done)} | to do: {len(todo)}", flush=True)

SYS = (
 "You are a biomedical information-extraction assistant. From the scientific poster text, "
 "extract EVERY biomarker that is mentioned or implicated. Interpret 'biomarker' BROADLY: any "
 "measurable biological indicator — molecular (gene, protein, transcript, miRNA, metabolite, lipid, "
 "methylation site, mutation/variant, gene signature), cellular, microbial, physiological, imaging, "
 "or digital — that is used or PROPOSED as an indicator of a biological/clinical state: disease "
 "presence, subtype, progression, prognosis, treatment/therapy response, exposure, toxicity, or risk. "
 "CRITICAL: include novel, candidate, putative, or merely IMPLICATED markers even if the text does not "
 "call them 'biomarker' and even if unvalidated (e.g. a gene whose expression the study links to an "
 "outcome; a metabolite that discriminates groups). Exclude non-biological 'markers' (e.g. astronomical, "
 "chemical spectra with no biological readout, population-genetics ancestry markers). "
 "Return STRICT JSON: {\"has_biomarkers\": bool, \"biomarkers\": [{\"name\": str, "
 "\"kind\": \"gene|protein|transcript|miRNA|metabolite|mutation|signature|imaging|physiological|cell|microbial|other\", "
 "\"status\": \"established|candidate|implicated\", \"role\": \"diagnostic|prognostic|predictive|risk|exposure|monitoring|unspecified\", "
 "\"evidence\": \"<=20-word basis from the text\"}]}. If none, return has_biomarkers=false and an empty list."
)

sem = asyncio.Semaphore(CONC)
out_f = open(OUT, "a")
lock = asyncio.Lock()
n_done = [0]; n_bio = [0]

async def one(client, rid, rec):
    async with sem:
        payload = {"model": MODEL, "temperature": 0,
                   "response_format": {"type": "json_object"},
                   "messages": [{"role": "system", "content": SYS},
                                {"role": "user", "content": rec["text"][:60000]}]}
        for attempt in range(4):
            try:
                r = await client.post("https://api.deepseek.com/chat/completions",
                                      headers={"Authorization": f"Bearer {KEY}"},
                                      json=payload, timeout=180)
                if r.status_code == 200:
                    data = json.loads(r.json()["choices"][0]["message"]["content"])
                    rec_out = {"id": rid, "doi": rec["doi"],
                               "has_biomarkers": bool(data.get("has_biomarkers")),
                               "biomarkers": data.get("biomarkers", [])}
                    async with lock:
                        out_f.write(json.dumps(rec_out, ensure_ascii=False) + "\n"); out_f.flush()
                        n_done[0] += 1
                        if rec_out["biomarkers"]: n_bio[0] += 1
                        if n_done[0] % 50 == 0:
                            print(f"  {n_done[0]}/{len(todo)} done, {n_bio[0]} with biomarkers", flush=True)
                    return
                if r.status_code in (429, 500, 502, 503):
                    await asyncio.sleep(2 * (attempt + 1)); continue
                print(f"  {rid}: HTTP {r.status_code} {r.text[:120]}", flush=True); return
            except Exception as e:
                await asyncio.sleep(2 * (attempt + 1))
        print(f"  {rid}: failed after retries", flush=True)

async def main():
    async with httpx.AsyncClient() as client:
        await asyncio.gather(*[one(client, rid, rec) for rid, rec in todo])
    print(f"done: {n_done[0]} newly processed, {n_bio[0]} with biomarkers -> {OUT}", flush=True)

asyncio.run(main())
