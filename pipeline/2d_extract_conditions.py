"""Condition-only DeepSeek pass over the Health+Life posters that had NO biomarker
in pass 1 (~1,562). Pulls the disease/condition(s) each poster studies, so we can
combine with the biomarker posters' conditions for a corpus-wide condition
frequency (what's discussed most across conferences). Resumable, concurrent.

Run: DEEPSEEK_API=... ~/poster-bot/.venv/bin/python deepseek_conditions.py
"""
import os, json, glob, asyncio, httpx

SCR = "/home/jme/scratch_ptf"
SRC = "/home/jme/Downloads/posters-export"
ANNO = f"{SCR}/annotations.jsonl"
DS_FIRST = f"{SCR}/deepseek_biomarkers.jsonl"
OUT = f"{SCR}/deepseek_conditions.jsonl"
KEY = os.environ["DEEPSEEK_API"]
CONC = 8
MODEL = "deepseek-chat"

F2D = {t["field_id"]: t["domain"] for t in json.load(open(f"{SCR}/openalex_topics.json"))}
REL = {"Health Sciences", "Life Sciences"}
ann = {json.loads(l)["id"]: json.loads(l) for l in open(ANNO)}
health_life = {i for i, a in ann.items() if F2D.get(a["field_id"]) in REL}
biomarker_pos = {json.loads(l)["id"] for l in open(DS_FIRST) if json.loads(l).get("biomarkers")}
target = health_life - biomarker_pos           # biomedical posters without a biomarker

def text_of(pj):
    ts = pj.get("titles") or []
    title = ts[0].get("title","") if ts else ""
    desc = " ".join((d.get("description","") or "") for d in (pj.get("descriptions") or []))
    c = pj.get("content")
    content = c if isinstance(c,str) else (json.dumps(c) if c else "")
    return f"{title}\n\n{desc}\n\n{content}".strip()

def year_of(pj):
    return pj.get("publicationYear") or (pj.get("conference") or {}).get("conferenceYear")

records = {}
for fp in sorted(glob.glob(f"{SRC}/*.ndjson")):
    for ln in open(fp):
        if not ln.strip(): continue
        d = json.loads(ln); rid = str(d["id"])
        if rid not in target: continue
        pj = d["posterJson"]
        if isinstance(pj, str): pj = json.loads(pj)
        records[rid] = {"text": text_of(pj), "year": year_of(pj)}

done = set()
if os.path.exists(OUT):
    done = {json.loads(l)["id"] for l in open(OUT)}
todo = [(rid, r) for rid, r in records.items() if rid not in done]
print(f"Health+Life: {len(health_life)} | biomarker+: {len(biomarker_pos)} | "
      f"condition target (no biomarker): {len(records)} | to do: {len(todo)}", flush=True)

SYS = (
 "You are extracting the DISEASE / DISORDER / health or biological CONDITION(S) that a scientific "
 "poster studies or addresses. Return the specific condition(s) that are the subject of the work "
 "(e.g. 'breast cancer', 'type 2 diabetes', 'Alzheimer's disease', 'sepsis', 'COVID-19'). Include a "
 "condition even if only implicated as the focus. Do NOT return methods, organisms, or fields as "
 "conditions. If the poster is not about any disease/health condition, return an empty list. "
 "Return STRICT JSON: {\"conditions\": [\"condition name\", ...]}."
)

sem = asyncio.Semaphore(CONC)
out_f = open(OUT, "a"); lock = asyncio.Lock(); n = [0]; n_cond = [0]

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
                    conds = data.get("conditions", [])
                    async with lock:
                        out_f.write(json.dumps({"id": rid, "year": rec["year"],
                                                "conditions": conds}, ensure_ascii=False) + "\n")
                        out_f.flush(); n[0] += 1
                        if conds: n_cond[0] += 1
                        if n[0] % 50 == 0:
                            print(f"  {n[0]}/{len(todo)}, {n_cond[0]} with a condition", flush=True)
                    return
                if r.status_code in (429, 500, 502, 503):
                    await asyncio.sleep(2*(attempt+1)); continue
                print(f"  {rid}: HTTP {r.status_code}", flush=True); return
            except Exception:
                await asyncio.sleep(2*(attempt+1))
        print(f"  {rid}: failed", flush=True)

async def main():
    async with httpx.AsyncClient() as client:
        await asyncio.gather(*[one(client, rid, rec) for rid, rec in todo])
    print(f"done: {n[0]} posters, {n_cond[0]} with a condition -> {OUT}", flush=True)

asyncio.run(main())
