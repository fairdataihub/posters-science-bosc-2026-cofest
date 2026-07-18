"""Enriched DeepSeek re-run over the biomarker-positive posters (~1,368).
For EACH biomarker pulls: acronym, synonyms, condition(s), specimen, role,
direction, measurement method, population, status + evidence — a catalogue for
downstream condition matching, and the acronym/synonym alias dictionary that
collapses our count data (Tier 3 controlled vocab). Full untruncated text.

Run: DEEPSEEK_API=... ~/poster-bot/.venv/bin/python deepseek_catalogue.py
"""
import os, json, glob, asyncio, httpx

SCR = "/home/jme/scratch_ptf"
SRC = "/home/jme/Downloads/posters-export"
DS_FIRST = f"{SCR}/deepseek_biomarkers.jsonl"      # first pass: which posters had biomarkers
ANNO = f"{SCR}/annotations.jsonl"
OUT = f"{SCR}/deepseek_catalogue.jsonl"
KEY = os.environ["DEEPSEEK_API"]
CONC = 8
MODEL = "deepseek-chat"

# posters that had >=1 biomarker in pass 1
positive = {json.loads(l)["id"] for l in open(DS_FIRST)
            if json.loads(l).get("biomarkers")}
# field/subfield/domain per poster (for catalogue metadata)
F2D = {t["field_id"]: t["domain"] for t in json.load(open(f"{SCR}/openalex_topics.json"))}
ann = {json.loads(l)["id"]: json.loads(l) for l in open(ANNO)}
ta = json.load(open(f"{SCR}/topic_assign.json"))["meta"]

def meta_of(pj, rid):
    ts = pj.get("titles") or []
    a = ann.get(rid, {})
    return {
        "title": (ts[0].get("title") if ts else "") or "",
        "year": pj.get("publicationYear") or (pj.get("conference") or {}).get("conferenceYear"),
        "field": a.get("field"), "domain": F2D.get(a.get("field_id")) if a else None,
        "subfield": ta.get(rid, {}).get("subfield"),
    }

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
        if rid not in positive: continue
        pj = d["posterJson"]
        if isinstance(pj, str): pj = json.loads(pj)
        records[rid] = {"doi": pj.get("doi"), "url": d.get("posterUrl"),
                        "text": text_of(pj), "meta": meta_of(pj, rid)}

done = set()
if os.path.exists(OUT):
    done = {json.loads(l)["id"] for l in open(OUT)}
todo = [(rid, r) for rid, r in records.items() if rid not in done]
print(f"biomarker-positive posters: {len(records)} | done: {len(done)} | to do: {len(todo)}", flush=True)

SYS = (
 "You are a biomedical curator building a biomarker catalogue from a scientific poster. "
 "Identify EVERY biomarker mentioned or implicated (broad: molecular, cellular, physiological, "
 "imaging, microbial, digital; include novel/candidate/putative markers, not just canonical ones). "
 "For EACH biomarker return a rich record. Use ONLY information supported by the text; use null when "
 "a field is not stated (do not invent). Return STRICT JSON:\n"
 "{\"biomarkers\": [{"
 "\"name\": \"primary name as used\", "
 "\"acronym\": \"abbreviation or null\", "
 "\"synonyms\": [\"other names / aliases / gene symbol / common name\"], "
 "\"kind\": \"gene|protein|transcript|miRNA|metabolite|lipid|mutation|signature|imaging|physiological|cell|microbial|other\", "
 "\"conditions\": [\"disease/condition(s) it is associated with in this poster\"], "
 "\"specimen\": \"sample type (blood|serum|plasma|tissue|saliva|urine|CSF|stool|...) or null\", "
 "\"role\": \"diagnostic|prognostic|predictive|risk|exposure|monitoring|response|safety|unspecified\", "
 "\"direction\": \"increased|decreased|altered|present|absent|unspecified\", "
 "\"method\": \"assay/measurement technique (qPCR|ELISA|IHC|NGS|mass spec|imaging|...) or null\", "
 "\"population\": \"cohort/species/disease group or null\", "
 "\"status\": \"established|candidate|implicated\", "
 "\"evidence\": \"<=25-word basis from the text\"}]}. "
 "If genuinely none, return {\"biomarkers\": []}."
)

sem = asyncio.Semaphore(CONC)
out_f = open(OUT, "a")
lock = asyncio.Lock()
n_done = [0]; n_bm = [0]

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
                                      json=payload, timeout=240)
                if r.status_code == 200:
                    data = json.loads(r.json()["choices"][0]["message"]["content"])
                    bms = data.get("biomarkers", [])
                    rec_out = {"id": rid, "doi": rec["doi"], "url": rec["url"],
                               **rec["meta"], "biomarkers": bms}
                    async with lock:
                        out_f.write(json.dumps(rec_out, ensure_ascii=False) + "\n"); out_f.flush()
                        n_done[0] += 1; n_bm[0] += len(bms)
                        if n_done[0] % 50 == 0:
                            print(f"  {n_done[0]}/{len(todo)} posters, {n_bm[0]} biomarker records", flush=True)
                    return
                if r.status_code in (429, 500, 502, 503):
                    await asyncio.sleep(2*(attempt+1)); continue
                print(f"  {rid}: HTTP {r.status_code} {r.text[:120]}", flush=True); return
            except Exception:
                await asyncio.sleep(2*(attempt+1))
        print(f"  {rid}: failed after retries", flush=True)

async def main():
    async with httpx.AsyncClient() as client:
        await asyncio.gather(*[one(client, rid, rec) for rid, rec in todo])
    print(f"done: {n_done[0]} posters, {n_bm[0]} biomarker records -> {OUT}", flush=True)

asyncio.run(main())
