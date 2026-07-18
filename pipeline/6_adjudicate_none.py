"""Stage 13b: DeepSeek adjudication of the AMBIGUOUS 'none' entities.
Each gets a reason_code: NOVEL_CANDIDATE | NOT_ENTITY | KNOWN_UNCATALOGUED |
UNRESOLVED, with is_biomarker_entity / is_novel / confidence. Batched, resumable.
"""
import os, json, asyncio, httpx

SCR = "/home/jme/scratch_ptf"
AMBIG = f"{SCR}/none_ambiguous.json"
OUT = f"{SCR}/none_adjudicated.jsonl"
KEY = os.environ["DEEPSEEK_API"]
BATCH = 30
CONC = 6
MODEL = "deepseek-chat"

items = json.load(open(AMBIG))
done = set()
if os.path.exists(OUT):
    done = {json.loads(l)["canonical"] for l in open(OUT)}
todo = [x for x in items if x["canonical"] not in done]
batches = [todo[i:i+BATCH] for i in range(0, len(todo), BATCH)]
print(f"ambiguous: {len(items)} | done: {len(done)} | batches: {len(batches)}", flush=True)

SYS = (
 "You are adjudicating candidate biomarker strings extracted from scientific posters. For EACH item "
 "decide a reason_code:\n"
 "- NOVEL_CANDIDATE: a bona fide MOLECULAR/measurable biomarker ENTITY (gene, protein, metabolite, "
 "transcript, miRNA, mutation, lipid, molecular signature) that is plausibly novel/candidate — NOT an "
 "established textbook marker.\n"
 "- KNOWN_UNCATALOGUED: a real biomarker ENTITY but an ESTABLISHED/well-known one (would be in a "
 "reference DB under some name); give its standard name/id if you know it.\n"
 "- NOT_ENTITY: NOT a biomarker entity — a method/assay, organism/taxon, disease/phenotype, anatomical "
 "term, covariate (age/BMI), generic phrase, lab tool/biosensor, or environmental metric.\n"
 "- UNRESOLVED: too ambiguous/underspecified to judge.\n"
 "Use the name, kind, and associated conditions as context. Return STRICT JSON: {\"results\":[{"
 "\"canonical\": <echo exactly>, \"reason_code\": \"NOVEL_CANDIDATE|KNOWN_UNCATALOGUED|NOT_ENTITY|UNRESOLVED\", "
 "\"is_biomarker_entity\": bool, \"is_novel\": bool, \"standard_name\": str|null, \"confidence\": \"high|medium|low\", "
 "\"note\": \"<=15 words\"}]}."
)

sem = asyncio.Semaphore(CONC)
out_f = open(OUT, "a"); lock = asyncio.Lock(); n = [0]

async def one(client, batch):
    async with sem:
        payload = {"model": MODEL, "temperature": 0, "response_format": {"type": "json_object"},
                   "messages": [{"role": "system", "content": SYS},
                                {"role": "user", "content": "ITEMS:\n" + json.dumps(
                                    [{"canonical": b["canonical"], "kind": b["kind"],
                                      "conditions": b["top_conditions"]} for b in batch], ensure_ascii=False)}]}
        for attempt in range(4):
            try:
                r = await client.post("https://api.deepseek.com/chat/completions",
                                      headers={"Authorization": f"Bearer {KEY}"}, json=payload, timeout=180)
                if r.status_code == 200:
                    res = json.loads(r.json()["choices"][0]["message"]["content"]).get("results", [])
                    got = {x.get("canonical"): x for x in res}
                    async with lock:
                        for b in batch:
                            x = got.get(b["canonical"], {"canonical": b["canonical"],
                                "reason_code": "UNRESOLVED", "confidence": "low", "note": "no verdict returned"})
                            out_f.write(json.dumps(x, ensure_ascii=False) + "\n")
                        out_f.flush(); n[0] += len(batch)
                        if n[0] % 120 == 0: print(f"  {n[0]}/{len(todo)}", flush=True)
                    return
                if r.status_code in (429,500,502,503):
                    await asyncio.sleep(2*(attempt+1)); continue
                print(f"  batch HTTP {r.status_code}", flush=True); return
            except Exception:
                await asyncio.sleep(2*(attempt+1))
        # fallback: write UNRESOLVED so nothing is lost
        async with lock:
            for b in batch:
                out_f.write(json.dumps({"canonical": b["canonical"], "reason_code": "UNRESOLVED",
                                        "confidence": "low", "note": "batch failed"}) + "\n")
            out_f.flush()

async def main():
    async with httpx.AsyncClient() as client:
        await asyncio.gather(*[one(client, b) for b in batches])
    print(f"done: {n[0]} adjudicated -> {OUT}", flush=True)

asyncio.run(main())
