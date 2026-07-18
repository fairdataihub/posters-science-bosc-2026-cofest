#!/usr/bin/env python3
"""Assemble the self-contained HTML artifact from analysis.json (exact data inlined)."""
import json, html
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"
a = json.loads((OUT / "analysis.json").read_text())

# hand-picked semantic-merge exemplars (honest showcase of fairly clustering value)
MERGES = [
    {"type": "Material", "canon": "phosphate-buffered saline",
     "variants": ["1X Phosphate Buffered Saline", "Dulbecco's PBS", "citrate buffer", "carbonate buffer"]},
    {"type": "Method", "canon": "Random Forest",
     "variants": ["random forest classifier", "Random Forest algorithm", "mixed effects random forest"]},
    {"type": "Metric", "canon": "gait speed",
     "variants": ["gait velocity", "4-metre gait speed", "gait speeds", "habitual gait speed"]},
    {"type": "Method", "canon": "semi-structured interviews",
     "variants": ["clinical interviews", "Semi-directed interviews", "Semi-structured 1-hour interviews"]},
    {"type": "Material", "canon": "Fusarium",
     "variants": ["F. oxysporum", "Fusarium circinatum", "Aspergillus flavus Fusarium spp"]},
    {"type": "Material", "canon": "striatum",
     "variants": ["dorsal striatum", "mouse striatum", "striatal connectome", "basal ganglia"]},
]

TYPE_META = {
    "Method":   {"slot": 1, "blurb": "techniques & analyses"},
    "Material": {"slot": 2, "blurb": "reagents, organisms, samples"},
    "Metric":   {"slot": 4, "blurb": "measures, scores, statistics"},
    "Tool":     {"slot": 3, "blurb": "software, instruments, databases"},
}
TYPE_ORDER = ["Method", "Material", "Metric", "Tool"]

data = {
    "corpus": a["corpus"],
    "dedup": a["dedup"],
    "top_by_type": {t: a["top_by_type"][t][:12] for t in TYPE_ORDER},
    "enriched": a["enriched"][:16],
    "type_meta": TYPE_META,
    "type_order": TYPE_ORDER,
    "merges": MERGES,
}

DATA_JSON = json.dumps(data, ensure_ascii=False)

HTML = """<title>The Methodology Landscape of Biomarker Discovery</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root{
  color-scheme: light;
  --surface:#fcfcfb; --panel:#f4f5f2; --panel-2:#eef0ec;
  --ink:#0b0b0b; --muted:#54574f; --faint:#8b8f85; --hair:#e2e5df;
  --s1:#2a78d6; --s2:#008300; --s3:#c74d81; --s4:#c98500;
  --s1-soft:#dfeafb; --s2-soft:#dcefdc; --s3-soft:#f7e2ec; --s4-soft:#f6ecd6;
  --shadow:0 1px 2px rgba(20,24,22,.05),0 8px 30px rgba(20,24,22,.05);
  --font-display:'Iowan Old Style','Palatino Linotype',Palatino,'Book Antiqua',Georgia,serif;
  --font-body:system-ui,-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
  --font-mono:ui-monospace,'SF Mono','Cascadia Code','JetBrains Mono',Menlo,Consolas,monospace;
}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])){
  color-scheme:dark;
  --surface:#14181a; --panel:#1c2225; --panel-2:#222a2d;
  --ink:#f2f4f2; --muted:#b3bab5; --faint:#7d857f; --hair:#2b3236;
  --s1:#3987e5; --s2:#3aa83a; --s3:#d76a99; --s4:#d9a23e;
  --s1-soft:#17304d; --s2-soft:#183a1a; --s3-soft:#3a2130; --s4-soft:#3a2f14;
  --shadow:0 1px 2px rgba(0,0,0,.3),0 10px 34px rgba(0,0,0,.35);
}}
:root[data-theme="dark"]{
  color-scheme:dark;
  --surface:#14181a; --panel:#1c2225; --panel-2:#222a2d;
  --ink:#f2f4f2; --muted:#b3bab5; --faint:#7d857f; --hair:#2b3236;
  --s1:#3987e5; --s2:#3aa83a; --s3:#d76a99; --s4:#d9a23e;
  --s1-soft:#17304d; --s2-soft:#183a1a; --s3-soft:#3a2130; --s4-soft:#3a2f14;
  --shadow:0 1px 2px rgba(0,0,0,.3),0 10px 34px rgba(0,0,0,.35);
}
*{box-sizing:border-box}
body{margin:0;background:var(--surface);color:var(--ink);font-family:var(--font-body);
  line-height:1.55;-webkit-font-smoothing:antialiased;overflow-x:hidden}
.wrap{max-width:1080px;margin:0 auto;padding:0 24px}
a{color:var(--s1);text-decoration:none;border-bottom:1px solid color-mix(in srgb,var(--s1) 35%,transparent)}
a:hover{border-bottom-color:var(--s1)}
.mono{font-family:var(--font-mono)}
.eyebrow{font-family:var(--font-mono);font-size:12px;letter-spacing:.14em;text-transform:uppercase;
  color:var(--faint)}
h1,h2,h3{font-family:var(--font-display);font-weight:600;text-wrap:balance;margin:0}
.num{font-variant-numeric:tabular-nums;font-family:var(--font-mono)}

/* theme toggle */
.toggle{position:fixed;top:16px;right:16px;z-index:50;font-family:var(--font-mono);font-size:12px;
  background:var(--panel);color:var(--muted);border:1px solid var(--hair);border-radius:999px;
  padding:7px 13px;cursor:pointer;box-shadow:var(--shadow)}
.toggle:hover{color:var(--ink)}
.toggle:focus-visible{outline:2px solid var(--s1);outline-offset:2px}

/* masthead */
header.mast{padding:74px 0 30px;border-bottom:1px solid var(--hair)}
.kicker{display:flex;align-items:center;gap:10px;margin-bottom:20px}
.kicker .dot{width:8px;height:8px;border-radius:2px;background:var(--s1)}
.kicker .dot:nth-child(2){background:var(--s2)}.kicker .dot:nth-child(3){background:var(--s4)}
.kicker .dot:nth-child(4){background:var(--s3)}
h1{font-size:clamp(30px,5vw,52px);line-height:1.05;letter-spacing:-.015em}
.dek{font-size:clamp(17px,2vw,20px);color:var(--muted);max-width:64ch;margin-top:18px;line-height:1.5}
.prov{margin-top:26px;font-family:var(--font-mono);font-size:12.5px;color:var(--faint);
  display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center}
.prov b{color:var(--muted);font-weight:600}
.prov .arw{color:var(--s1)}

/* KPI tiles */
.kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:14px;margin:34px 0 8px}
.kpi{background:var(--panel);border:1px solid var(--hair);border-radius:12px;padding:16px 16px 15px}
.kpi .v{font-family:var(--font-mono);font-size:clamp(20px,2.4vw,27px);font-weight:600;letter-spacing:-.02em;
  font-variant-numeric:tabular-nums}
.kpi .k{font-size:12px;color:var(--muted);margin-top:5px;line-height:1.35}
.kpi .sub{font-family:var(--font-mono);font-size:11px;color:var(--faint);margin-top:3px}

section{padding:46px 0;border-bottom:1px solid var(--hair)}
.sec-head{max-width:70ch;margin-bottom:26px}
.sec-head h2{font-size:clamp(23px,3vw,32px);letter-spacing:-.01em;line-height:1.1}
.sec-head p{color:var(--muted);margin:12px 0 0;font-size:15.5px}

/* toolkit grid */
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:18px}
.panel{background:var(--panel);border:1px solid var(--hair);border-radius:14px;padding:20px 20px 16px;
  box-shadow:var(--shadow)}
.panel-head{display:flex;align-items:baseline;justify-content:space-between;gap:10px;margin-bottom:16px}
.badge{font-family:var(--font-mono);font-size:11.5px;letter-spacing:.06em;text-transform:uppercase;
  padding:3px 9px;border-radius:6px;font-weight:600}
.badge.Method{background:var(--s1-soft);color:var(--s1)}
.badge.Material{background:var(--s2-soft);color:var(--s2)}
.badge.Metric{background:var(--s4-soft);color:var(--s4)}
.badge.Tool{background:var(--s3-soft);color:var(--s3)}
.panel-head .blurb{font-size:12.5px;color:var(--faint)}
.bars{display:flex;flex-direction:column;gap:7px}
.bar{display:grid;grid-template-columns:130px 1fr auto;align-items:center;gap:10px;cursor:default}
.bar .lab{font-size:13px;color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bar .track{height:11px;border-radius:0 4px 4px 0;position:relative;background:transparent}
.bar .fill{height:100%;border-radius:0 4px 4px 0}
.fill,.efill,.ded-fill{display:block;transform-origin:left;animation:reveal .7s cubic-bezier(.2,.7,.2,1) both}
@keyframes reveal{from{transform:scaleX(0)}to{transform:scaleX(1)}}
.bar .cnt{font-family:var(--font-mono);font-size:12px;color:var(--muted);font-variant-numeric:tabular-nums;
  min-width:30px;text-align:right}
.fill.Method{background:var(--s1)}.fill.Material{background:var(--s2)}
.fill.Metric{background:var(--s4)}.fill.Tool{background:var(--s3)}

/* enrichment */
.enrich{display:flex;flex-direction:column;gap:9px}
.erow{display:grid;grid-template-columns:190px 1fr 74px;align-items:center;gap:12px}
.erow .lab{display:flex;align-items:center;gap:8px;font-size:13.5px;white-space:nowrap;overflow:hidden}
.erow .lab .tag{width:9px;height:9px;border-radius:2px;flex:none}
.tag.Method{background:var(--s1)}.tag.Material{background:var(--s2)}
.tag.Metric{background:var(--s4)}.tag.Tool{background:var(--s3)}
.erow .etrack{height:15px;background:var(--panel-2);border-radius:4px;overflow:hidden}
.erow .efill{height:100%;border-radius:4px}
.efill.Method{background:var(--s1)}.efill.Material{background:var(--s2)}
.efill.Metric{background:var(--s4)}.efill.Tool{background:var(--s3)}
.erow .lift{font-family:var(--font-mono);font-size:12.5px;text-align:right;font-variant-numeric:tabular-nums}
.erow .lift b{font-weight:600}.erow .lift .n{color:var(--faint);font-size:11px}
.axisnote{font-family:var(--font-mono);font-size:11px;color:var(--faint);margin-top:14px;
  display:flex;justify-content:space-between}

/* cleaning */
.clean-grid{display:grid;grid-template-columns:1fr 1fr;gap:26px;align-items:start}
.ded{display:flex;flex-direction:column;gap:14px}
.ded-row .dtop{display:flex;justify-content:space-between;font-size:13px;margin-bottom:5px}
.ded-row .dtop .rt{font-family:var(--font-mono);color:var(--muted);font-variant-numeric:tabular-nums}
.ded-bar{height:9px;background:var(--panel-2);border-radius:5px;overflow:hidden;position:relative}
.ded-fill{height:100%;border-radius:5px}
.merges{display:flex;flex-direction:column;gap:12px}
.merge{background:var(--panel);border:1px solid var(--hair);border-radius:10px;padding:12px 13px}
.merge .to{display:flex;align-items:center;gap:8px;font-size:14px;font-weight:600;margin-bottom:7px}
.merge .vars{display:flex;flex-wrap:wrap;gap:6px}
.chip{font-family:var(--font-mono);font-size:11.5px;color:var(--muted);background:var(--panel-2);
  border-radius:5px;padding:3px 8px}
.chip.gone{text-decoration:line-through;text-decoration-color:var(--faint);opacity:.7}
.holdout{margin-top:20px;background:var(--panel);border:1px dashed var(--hair);border-radius:10px;
  padding:14px 15px;font-size:13.5px;color:var(--muted)}
.holdout b{color:var(--ink)}
.holdout .pair{font-family:var(--font-mono);color:var(--s1)}

details{margin-top:20px}
summary{font-family:var(--font-mono);font-size:12px;color:var(--faint);cursor:pointer;list-style:none}
summary::-webkit-details-marker{display:none}
summary::before{content:"▸ ";color:var(--s1)}
details[open] summary::before{content:"▾ "}
table{border-collapse:collapse;margin-top:12px;font-size:12.5px;width:100%;font-variant-numeric:tabular-nums}
th,td{text-align:left;padding:5px 12px 5px 0;border-bottom:1px solid var(--hair)}
th{font-family:var(--font-mono);font-weight:600;color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.05em}
td.n{font-family:var(--font-mono);text-align:right;padding-right:18px}
.tbl-scroll{overflow-x:auto}

footer{padding:40px 0 70px;color:var(--muted);font-size:13.5px}
footer .files{font-family:var(--font-mono);font-size:12px;color:var(--faint);margin-top:14px;line-height:1.9}
.cite{margin-top:18px;padding:14px 16px;background:var(--panel);border-left:3px solid var(--s1);
  border-radius:0 8px 8px 0;font-size:13px;color:var(--muted)}

/* tooltip */
#tip{position:fixed;pointer-events:none;z-index:80;background:var(--ink);color:var(--surface);
  font-family:var(--font-mono);font-size:11.5px;padding:6px 9px;border-radius:6px;opacity:0;
  transition:opacity .12s;max-width:260px;box-shadow:var(--shadow)}
@media (max-width:760px){
  .kpis{grid-template-columns:repeat(2,1fr)}
  .grid2,.clean-grid{grid-template-columns:1fr}
  .bar{grid-template-columns:112px 1fr auto}
  .erow{grid-template-columns:140px 1fr 66px}
}
@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
</style>

<button class="toggle" id="themeBtn" aria-label="Toggle color theme">◐ theme</button>
<div id="tip" role="status"></div>

<header class="mast"><div class="wrap">
  <div class="kicker"><span class="dot"></span><span class="dot"></span><span class="dot"></span><span class="dot"></span>
    <span class="eyebrow">PubVerse NER &nbsp;×&nbsp; fair-ly-accurate &nbsp;·&nbsp; BOSC CoFest 2026</span></div>
  <h1>The methodology landscape of biomarker discovery</h1>
  <p class="dek">A distilled scientific NER model read the full text of <b>2,929</b> recent biomedical
  posters and surfaced the <b>methods, materials, metrics, and tools</b> behind the biomarker hunt —
  then <b>fair-ly-accurate</b> collapsed the surface-form noise into a clean, countable catalogue.</p>
  <div class="prov" id="prov"></div>
</div></header>

<div class="wrap">
  <div class="kpis" id="kpis"></div>
</div>

<section><div class="wrap">
  <div class="sec-head">
    <h2>The four-channel toolkit</h2>
    <p>Every entity the model tagged, folded to a canonical form and ranked by how many posters use it.
    Four channels, one per entity type — the working vocabulary of 2024–present biomarker research.</p>
  </div>
  <div class="grid2" id="toolkit"></div>
  <details><summary>View as table</summary><div class="tbl-scroll" id="toolkitTable"></div></details>
</div></section>

<section><div class="wrap">
  <div class="sec-head">
    <h2>What signals a biomarker</h2>
    <p>Of the 2,929 posters, <b id="brate">47%</b> report at least one biomarker. These entities skew hardest
    toward that group — a poster mentioning them is up to <b>2.1×</b> more likely to carry a biomarker than
    the corpus baseline. Molecular assays and clinical measures lead; the pattern is a sanity check that the
    NER read the biology, not the layout. <span class="mono" style="color:var(--faint)">(≥20 posters; ranked by Wilson-adjusted rate.)</span></p>
  </div>
  <div class="enrich" id="enrich"></div>
  <div class="axisnote"><span>baseline 1.0× &nbsp;→</span><span>2.2× enrichment</span></div>
  <details><summary>View as table</summary><div class="tbl-scroll" id="enrichTable"></div></details>
</div></section>

<section><div class="wrap">
  <div class="sec-head">
    <h2>Polishing the pull, three tiers deep</h2>
    <p>Raw NER emits every spelling and phrasing as its own entity. fair-ly-accurate's synonym-lustre
    (<span class="mono">gte-large-en-v1.5 → HDBSCAN → most-frequent form</span>) collapses them — with an
    <b>acronym holdout</b> so short forms are never wrongly merged.</p>
  </div>
  <div class="clean-grid">
    <div>
      <div class="eyebrow" style="margin-bottom:14px">Distinct surfaces → canonical entities</div>
      <div class="ded" id="ded"></div>
      <div class="holdout">
        <b>The holdout guard.</b> Short/all-caps tokens sit out the clustering, so
        <span class="pair">IL-6</span> never fuses with <span class="pair">IL-8</span>, and
        <span class="pair">PCR</span> stays whole. A conservative <span class="mono">ε&nbsp;=&nbsp;0.12</span>
        keeps distinct methods apart.
      </div>
    </div>
    <div>
      <div class="eyebrow" style="margin-bottom:14px">Selected merges (variant → canonical)</div>
      <div class="merges" id="merges"></div>
    </div>
  </div>
</div></section>

<footer><div class="wrap">
  <div class="eyebrow" style="margin-bottom:12px">Provenance</div>
  <div>Model <a href="https://huggingface.co/jimnoneill/pubverse-ner-distilled">jimnoneill/pubverse-ner-distilled</a>
  (IDCNN + CRF over potion-science-32M static embeddings, 4 entity types, span-F1 0.736) run on the full
  title + description + OCR content of every poster. Names normalized with
  <a href="https://github.com/fairdataihub/fair-ly-accurate-text-synonyms-for-data-cleaning">fair-ly-accurate</a>.
  Source corpus: the 2,929 Health + Life Sciences posters (2024+) from
  <a href="https://posters.science">posters.science</a>.</div>
  <div class="files" id="files"></div>
  <div class="cite">Posters-are-cool — O'Neill, Kulkarni, Smith, Awe, Patel. BOSC 2026 CollaborationFest.
  This NER read is complementary to the DeepSeek biomarker extraction: it maps the <i>how</i>
  (methods, tools, materials, metrics) rather than the <i>what</i> (biomarkers).</div>
</div></footer>

<script id="data" type="application/json">__DATA__</script>
<script>
const D = JSON.parse(document.getElementById('data').textContent);
const fmt = n => n.toLocaleString('en-US');

// theme toggle
const btn = document.getElementById('themeBtn'), root = document.documentElement;
btn.onclick = () => {
  const cur = root.getAttribute('data-theme')
    || (matchMedia('(prefers-color-scheme:dark)').matches ? 'dark' : 'light');
  root.setAttribute('data-theme', cur === 'dark' ? 'light' : 'dark');
};

// tooltip
const tip = document.getElementById('tip');
function bindTip(el, textFn){
  el.addEventListener('mousemove', e => {
    tip.textContent = textFn(); tip.style.opacity = 1;
    const x = Math.min(e.clientX + 14, innerWidth - tip.offsetWidth - 10);
    tip.style.left = x + 'px'; tip.style.top = (e.clientY + 16) + 'px';
  });
  el.addEventListener('mouseleave', () => tip.style.opacity = 0);
}

// provenance strip
const steps = ['31,417 posters','field-classified','2,929 biomedical','189,055 sentences',
  '106,032 entities','34,411 canonical'];
document.getElementById('prov').innerHTML = steps.map((s,i)=>
  (i?'<span class="arw">→</span>':'')+'<span'+(i?'':' ')+'>'+(i===0?'<b>'+s+'</b>':s)+'</span>'
).join(' ');

// KPIs
const c = D.corpus, d = D.dedup;
const rawTot = Object.values(d.raw_unique_by_type).reduce((a,b)=>a+b,0);
const clnTot = Object.values(d.clean_unique_by_type).reduce((a,b)=>a+b,0);
const kpis = [
  {v: fmt(c.posters), k:'biomedical posters read', sub:'Health + Life Sci, 2024+'},
  {v: fmt(c.total_mentions), k:'entity mentions tagged', sub:fmt(c.sentences)+' sentences'},
  {v: fmt(rawTot)+'→'+fmt(clnTot), k:'surfaces → canonical', sub:'−'+Math.round(100*(1-clnTot/rawTot))+'% after cleaning'},
  {v: Math.round(c.base_rate*100)+'%', k:'report ≥1 biomarker', sub:fmt(c.posters_biomarker_positive)+' posters'},
  {v: '725/s', k:'sentence throughput', sub:'static emb · 1 GPU'},
];
document.getElementById('kpis').innerHTML = kpis.map(k=>
  `<div class="kpi"><div class="v num">${k.v}</div><div class="k">${k.k}</div><div class="sub">${k.sub}</div></div>`).join('');
document.getElementById('brate').textContent = Math.round(c.base_rate*100)+'%';

// toolkit
const tk = document.getElementById('toolkit');
D.type_order.forEach(t=>{
  const rows = D.top_by_type[t], max = Math.max(...rows.map(r=>r.posters));
  const meta = D.type_meta[t];
  const p = document.createElement('div'); p.className='panel';
  p.innerHTML = `<div class="panel-head"><span class="badge ${t}">${t}</span>
    <span class="blurb">${meta.blurb}</span></div><div class="bars"></div>`;
  const bars = p.querySelector('.bars');
  rows.forEach(r=>{
    const b = document.createElement('div'); b.className='bar';
    b.innerHTML = `<span class="lab" title="${r.name}">${r.name}</span>
      <span class="track"><span class="fill ${t}"></span></span>
      <span class="cnt">${r.posters}</span>`;
    bars.appendChild(b);
    b.querySelector('.fill').style.width = (100*r.posters/max)+'%';
    bindTip(b, ()=>`${r.name} — ${r.posters} posters · ${fmt(r.mentions)} mentions`);
  });
  tk.appendChild(p);
});

// toolkit table
let tt = '<table><thead><tr><th>Type</th><th>Entity</th><th>Posters</th><th>Mentions</th></tr></thead><tbody>';
D.type_order.forEach(t=> D.top_by_type[t].forEach(r=>{
  tt += `<tr><td><span class="badge ${t}">${t}</span></td><td>${r.name}</td>
    <td class="n">${r.posters}</td><td class="n">${fmt(r.mentions)}</td></tr>`;
}));
document.getElementById('toolkitTable').innerHTML = tt + '</tbody></table>';

// enrichment
const en = D.enriched, emax = Math.max(...en.map(e=>e.lift));
const ec = document.getElementById('enrich');
en.forEach(e=>{
  const row = document.createElement('div'); row.className='erow';
  row.innerHTML = `<span class="lab"><span class="tag ${e.type}"></span>${e.name}</span>
    <span class="etrack"><span class="efill ${e.type}"></span></span>
    <span class="lift"><b>${e.lift.toFixed(1)}×</b> <span class="n">n=${e.posters}</span></span>`;
  ec.appendChild(row);
  // anchor at the meaningful 1.0x baseline so 1.8-2.1x differences are visible
  row.querySelector('.efill').style.width = (100*(e.lift-1)/(emax-1))+'%';
  bindTip(row, ()=>`${e.name} (${e.type}) — in ${e.posters} posters, ${Math.round(e.p_bio*100)}% carry a biomarker · ${e.lift.toFixed(2)}× baseline`);
});
let et = '<table><thead><tr><th>Entity</th><th>Type</th><th>Posters</th><th>% biomarker+</th><th>Lift</th></tr></thead><tbody>';
en.forEach(e=> et += `<tr><td>${e.name}</td><td>${e.type}</td><td class="n">${e.posters}</td>
  <td class="n">${Math.round(e.p_bio*100)}%</td><td class="n">${e.lift.toFixed(2)}×</td></tr>`);
document.getElementById('enrichTable').innerHTML = et + '</tbody></table>';

// dedup bars
const ded = document.getElementById('ded');
D.type_order.forEach(t=>{
  const raw = d.raw_unique_by_type[t], cln = d.clean_unique_by_type[t];
  const row = document.createElement('div'); row.className='ded-row';
  row.innerHTML = `<div class="dtop"><span><span class="badge ${t}">${t}</span></span>
    <span class="rt">${fmt(raw)} → ${fmt(cln)} &nbsp;(−${d.reduction_pct[t]}%)</span></div>
    <div class="ded-bar"><span class="ded-fill fill ${t}"></span></div>`;
  ded.appendChild(row);
  row.querySelector('.ded-fill').style.width = (100*cln/raw)+'%';
  bindTip(row, ()=>`${t}: ${fmt(raw)} raw surfaces collapsed to ${fmt(cln)} canonical entities`);
});

// merges
document.getElementById('merges').innerHTML = D.merges.map(m=>
  `<div class="merge"><div class="to"><span class="tag ${m.type}"></span>${m.canon}</div>
   <div class="vars">${m.variants.map(v=>`<span class="chip gone">${v}</span>`).join('')}</div></div>`
).join('');

// files
document.getElementById('files').innerHTML = [
 'poster_entities_clean.ndjson — per-poster entities (canonical)',
 'clean_entities.tsv — canonical × type × freq × merged variants',
 'analysis.json — toolkit, enrichment, dedup stats',
 'fairly_review.{Method,Material,Metric,Tool}.tsv — human-review gates',
].map(s=>'· '+s).join('<br>');
</script>
"""

html_out = HTML.replace("__DATA__", DATA_JSON)
(OUT / "methodology_landscape.html").write_text(html_out)
print("wrote", OUT / "methodology_landscape.html", f"({len(html_out):,} bytes)")
