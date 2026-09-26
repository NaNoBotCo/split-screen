"""site.py — build/site from the catalog: four tile walls, the math, a home page.

    python tools/site.py
"""
from __future__ import annotations

import datetime as dt
import html
import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "build" / "site"
SITE_URL = os.environ.get("SITE_URL", "https://nanobotco.github.io/split-screen").rstrip("/")
sys.path.insert(0, str(ROOT / "vision"))
import doom  # noqa: E402

START = "2023-09-26"
WALLS = [
    # slug, class, English, Thai, one line
    ("left", "rfk_left", "RFK left", "RFK อยู่ซ้าย", "His face on the left, the thing on the right."),
    ("right", "rfk_right", "RFK right", "RFK อยู่ขวา", "The same cut, flipped: the thing on the left, his face on the right."),
    ("thing", "thing_only", "The thing", "เฉพาะของ", "The thing alone on a thing story, no face of his."),
    ("face", "rfk_only", "RFK", "เฉพาะ RFK", "His face on a thing story, nothing beside it."),
]
THING_TH = {
    "sugar": "น้ำตาล", "soda": "น้ำอัดลม", "candy": "ลูกอม", "food dye": "สีผสมอาหาร", "cereal": "ซีเรียล",
    "donuts & cake": "โดนัท/เค้ก", "ice cream": "ไอศกรีม", "chips & snacks": "ขนมกรุบกรอบ", "fast food": "ฟาสต์ฟู้ด",
    "processed meat": "เนื้อแปรรูป", "seed oil": "น้ำมันพืช", "milk": "นม", "infant formula": "นมผง",
    "water & fluoride": "น้ำ/ฟลูออไรด์", "alcohol": "เหล้าเบียร์", "tobacco & vapes": "บุหรี่/พอด",
    "energy drinks": "เครื่องดื่มชูกำลัง", "pills & painkillers": "ยาเม็ด", "vaccines": "วัคซีน",
    "sweeteners": "สารให้ความหวาน", "school lunch": "อาหารกลางวันโรงเรียน", "plated food": "อาหารจานเดียว",
    "sunscreen & cosmetics": "ครีมกันแดด/เครื่องสำอาง", "phones & screens": "มือถือ/จอ",
    "eggs": "ไข่", "produce": "ผักผลไม้", "raw meat": "เนื้อดิบ", "germs & disease": "เชื้อโรค", "pet food": "อาหารสัตว์",
    "chemicals": "สารเคมี",
}

CSS = """
:root{--bg:#0b0b0f;--bg2:#111118;--panel:#16161f;--ink:#f4f1ea;--mute:#aaa497;--line:#2b2b38;--chip:#1d1d29;
 --hot:#ff5a4e;--sugar:#fff4e0;--gold:#ffd27a;--blue:#8fd0ff;
 --display:"Avenir Next Condensed","HelveticaNeue-CondensedBold","Arial Narrow Bold",Impact,system-ui,sans-serif;
 --body:"Avenir Next",Avenir,"Segoe UI",system-ui,-apple-system,"Thonburi","Tahoma",sans-serif;
 --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;color-scheme:dark}
*{box-sizing:border-box}html{font-size:18px;background:var(--bg)}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--body);line-height:1.55}
a{color:var(--gold);text-underline-offset:.18em}a:hover{color:#fff}
a:focus-visible,button:focus-visible,select:focus-visible,input:focus-visible{outline:3px solid var(--gold);outline-offset:2px}
header.top{position:sticky;top:0;z-index:20;background:color-mix(in srgb,var(--bg) 88%,transparent);
 backdrop-filter:blur(10px);border-bottom:1px solid var(--line)}
header.top .in{max-width:84rem;margin:0 auto;padding:.5rem 1rem;display:flex;flex-wrap:wrap;gap:.3rem 1.1rem;align-items:center}
.brand{font-family:var(--display);font-weight:800;text-transform:uppercase;font-size:1.25rem;text-decoration:none;color:var(--ink);
 display:flex;align-items:center;gap:.5rem}
.brand i{display:inline-flex;width:1.5rem;height:1rem;border-radius:3px;overflow:hidden;box-shadow:0 0 0 2px var(--hot)}
.brand i:before,.brand i:after{content:"";flex:1}.brand i:before{background:#c9b8a6}.brand i:after{background:var(--sugar)}
nav{display:flex;flex-wrap:wrap;gap:.2rem .8rem;font-size:.78rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em}
nav a{color:var(--mute);text-decoration:none;padding:.15rem 0}nav a[aria-current],nav a:hover{color:var(--ink);box-shadow:inset 0 -3px 0 var(--hot)}
nav a span{font-weight:400;text-transform:none;letter-spacing:0;margin-left:.25rem;opacity:.75}
main{max-width:84rem;margin:0 auto;padding:1rem 1rem 5rem}
h1{font-family:var(--display);text-transform:uppercase;font-weight:800;font-size:clamp(2.2rem,7vw,4.4rem);line-height:.95;margin:.6rem 0 .3rem}
h1 small{display:block;font-size:.34em;color:var(--hot);letter-spacing:.25em;margin-bottom:.5rem}
h2{font-family:var(--display);text-transform:uppercase;font-weight:800;font-size:clamp(1.3rem,3vw,1.8rem);margin:2.2rem 0 .5rem;
 border-bottom:2px solid var(--line);padding-bottom:.2rem}
h2 .th,h1 .th{font-family:var(--body);text-transform:none;font-weight:500;color:var(--mute);font-size:.55em;margin-left:.5rem}
h1 .th{display:block;margin:.35rem 0 0;font-size:.32em}
p{max-width:46rem;margin:.55rem 0}.mute{color:var(--mute)}.small{font-size:.84rem}
.lede{font-size:clamp(1.05rem,2.2vw,1.3rem);max-width:48rem}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(10rem,1fr));gap:.6rem;margin:1rem 0}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:.7rem .8rem}
.stat b{display:block;font-family:var(--display);font-size:2rem;line-height:1;color:var(--ink)}
.stat span{font-size:.78rem;color:var(--mute)}
.doors{display:grid;grid-template-columns:repeat(auto-fit,minmax(15rem,1fr));gap:.8rem;margin:1rem 0}
.door{display:block;text-decoration:none;color:var(--ink);background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:hidden}
.door:hover{border-color:var(--hot)}
.door .strip{display:grid;grid-template-columns:repeat(3,1fr);aspect-ratio:3/1;background:#000}
.door .strip img{width:100%;height:100%;object-fit:cover}
.door div.t{padding:.6rem .8rem}.door b{font-family:var(--display);font-size:1.35rem;text-transform:uppercase}
.door .n{float:right;font-family:var(--display);font-size:1.35rem;color:var(--hot)}
.bar{display:flex;flex-wrap:wrap;gap:.5rem .8rem;align-items:center;margin:.8rem 0 1rem;font-size:.85rem;
 position:sticky;top:3.1rem;z-index:10;background:var(--bg);padding:.5rem 0;border-bottom:1px solid var(--line)}
.bar select,.bar input[type=search]{background:var(--chip);color:var(--ink);border:1px solid var(--line);border-radius:6px;padding:.35rem .5rem;font:inherit}
.bar label{display:flex;align-items:center;gap:.35rem}
.bar .count{margin-left:auto;color:var(--mute)}
.chips{display:flex;flex-wrap:wrap;gap:.3rem}.chip{background:var(--chip);border:1px solid var(--line);color:var(--ink);border-radius:99px;
 padding:.15rem .6rem;font:inherit;font-size:.8rem;cursor:pointer}.chip[aria-pressed=true]{background:var(--hot);border-color:var(--hot);color:#000}
.wall{display:grid;grid-template-columns:repeat(auto-fill,minmax(13rem,1fr));gap:.6rem}
.tile{background:var(--panel);border:1px solid var(--line);border-radius:10px;overflow:hidden;display:flex;flex-direction:column;cursor:pointer;
 text-align:left;color:inherit;font:inherit;padding:0}
.tile:hover{border-color:var(--hot)}
.tile img{width:100%;aspect-ratio:16/10;object-fit:cover;background:#000;display:block}
.tile .cap{padding:.45rem .55rem .55rem;font-size:.78rem;line-height:1.35}
.tile .meta{display:flex;flex-wrap:wrap;justify-content:space-between;gap:0 .5rem;color:var(--mute);font-size:.72rem;margin-bottom:.2rem}
.tile .meta span:last-child{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:100%}
.tile .h{display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.doom{height:4px;background:var(--line);border-radius:2px;margin-top:.35rem;overflow:hidden}.doom i{display:block;height:100%;background:var(--hot)}
.fam{background:var(--hot);color:#000;border-radius:99px;padding:0 .4rem;font-weight:700}
.more{display:block;margin:1.2rem auto;background:var(--chip);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:.6rem 1.2rem;font:inherit;cursor:pointer}
dialog{background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:12px;max-width:min(52rem,94vw);padding:0}
dialog::backdrop{background:rgba(0,0,0,.8)}
dialog img{width:100%;display:block;background:#000;max-height:70vh;object-fit:contain}
dialog .body{padding:.8rem 1rem 1rem;font-size:.9rem}dialog .x{float:right;background:none;border:0;color:var(--ink);font-size:1.5rem;cursor:pointer}
table{border-collapse:collapse;font-size:.85rem;margin:.6rem 0;width:100%;max-width:46rem}
th,td{border-bottom:1px solid var(--line);padding:.3rem .5rem;text-align:left;vertical-align:top}th{color:var(--mute);font-weight:600}
td.n{text-align:right;font-variant-numeric:tabular-nums}
.chart{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:.6rem;margin:.8rem 0;max-width:60rem}
.chart svg{width:100%;height:auto;display:block}
dfn{font-style:normal;border-bottom:1px dotted var(--mute)}
code{font-family:var(--mono);font-size:.88em;background:var(--chip);padding:.05em .3em;border-radius:4px}
footer{border-top:1px solid var(--line);background:var(--bg2);color:var(--mute);font-size:.8rem}
footer .in{max-width:84rem;margin:0 auto;padding:1.2rem 1rem 3rem}footer a{color:var(--mute)}
@media (max-width:40rem){html{font-size:16px}.wall{grid-template-columns:repeat(2,1fr)}.bar{top:auto;position:static}}
"""


def esc(s):
    return html.escape(s or "", quote=True)


def page(path: str, title: str, desc: str, body: str, current: str = "") -> None:
    depth = path.count("/")
    up = "../" * depth
    links = [("", "Home", "หน้าแรก")] + [(w[0] + "/", w[2], w[3]) for w in WALLS] + [("math/", "Math", "คณิต"), ("data/", "Data", "ข้อมูล")]
    nav = "".join(f'<a href="{up}{h}"{" aria-current=page" if h == current else ""}>{esc(e)}<span lang="th">{esc(t)}</span></a>'
                  for h, e, t in links)
    url = f"{SITE_URL}/{path.rsplit('index.html', 1)[0]}"
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{url}">
<meta property="og:type" content="website"><meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}"><meta property="og:url" content="{url}">
<meta property="og:image" content="{SITE_URL}/card.jpg"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:image" content="{SITE_URL}/card.jpg">
<link rel="icon" href="{up}icon.svg"><style>{CSS}</style></head><body>
<header class="top"><div class="in"><a class="brand" href="{up}"><i></i>Split Screen</a><nav>{nav}</nav></div></header>
<main>{body}</main>
<footer><div class="in"><p>Split Screen catalogs pictures posted beside Robert F. Kennedy Jr., {START} to today:
Bluesky posts and news articles (GDELT) that name him. Each tile links to where it was posted.
Pictures belong to their owners; tiles are 320-pixel thumbnails for comparison.</p>
<p lang="th">รวมภาพที่โพสต์คู่กับ RFK Jr. ตั้งแต่ 26 ก.ย. 2566 ถึงวันนี้ แต่ละภาพลิงก์ไปยังโพสต์ต้นทาง</p>
<p>Code MIT · words and numbers CC BY 4.0 · <a href="{up}data/">data</a></p></div></footer>
</body></html>"""
    p = OUT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(doc)


def load():
    con = sqlite3.connect(ROOT / "data" / "catalog.sqlite")
    q = """SELECT i.source, i.post_url, i.author, i.posted_at, i.text, i.headline, i.domain,
                  coalesce(i.likes,0)+coalesce(i.reposts,0)+coalesce(i.quotes,0), i.sha1, v.klass, v.thing_label,
                  v.thing_score, v.rfk_any, g.path, g.phash
           FROM items i JOIN vision v ON v.sha1=i.sha1 JOIN images g ON g.sha1=i.sha1
           WHERE v.klass != 'other' AND i.posted_at >= ?"""
    return con.execute(q, (START,)).fetchall()


def thumbs(rows):
    d = OUT / "img"
    d.mkdir(parents=True, exist_ok=True)
    for sha, path in {r[8]: r[13] for r in rows}.items():
        t = d / f"{sha}.jpg"
        if t.exists() or not path:
            continue
        src = ROOT / path
        if not src.exists():
            continue
        im = Image.open(src).convert("RGB")
        im.thumbnail((320, 320))
        im.save(t, "JPEG", quality=74, optimize=True)


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "data").mkdir(parents=True)
    rows = load()
    math = json.loads((ROOT / "data" / "math.json").read_text()) if (ROOT / "data" / "math.json").exists() else {}
    thumbs(rows)
    famsize = {}
    fam_of = {}
    # families as math.py drew them: reuse its sha1 -> size where present
    for k, c in (math.get("classes") or {}).items():
        for f in c.get("top_families", []):
            famsize[f["sha1"]] = f["size"]
    walls = {w[1]: [] for w in WALLS}
    for (src, url, author, at, text, head, domain, eng, sha, klass, thing, tscore, rfk, path, ph) in rows:
        words = " ".join(x for x in (head, text) if x)
        dscore, hits = doom.score(words)
        walls[klass].append({"s": sha, "d": at[:10], "u": url, "a": author if src == "bsky" else domain,
                             "src": src, "h": (((text or head) if src == "bsky" else (head or text)) or "")[:280], "t": thing, "ts": round(tscore or 0, 3),
                             "r": round(rfk or 0, 3), "doom": dscore, "e": eng, "p": ph})
    for w in WALLS:
        items = sorted(walls[w[1]], key=lambda x: x["d"], reverse=True)
        # sightings of one picture fold into its phash family in the browser; ship the phash
        (OUT / "data" / f"{w[0]}.json").write_text(json.dumps(items, separators=(",", ":")))
    counts = {w[1]: len(walls[w[1]]) for w in WALLS}
    pics = {w[1]: len({x["s"] for x in walls[w[1]]}) for w in WALLS}

    # home
    def strip(klass):
        ims = []
        seen = set()
        for x in sorted(walls[klass], key=lambda x: (-x["doom"], x["d"])):
            if x["s"] in seen:
                continue
            seen.add(x["s"])
            ims.append(f'<img src="img/{x["s"]}.jpg" alt="" loading="lazy">')
            if len(ims) == 3:
                break
        return "".join(ims)

    doors = "".join(
        f'<a class="door" href="{w[0]}/"><div class="strip">{strip(w[1])}</div><div class="t"><span class="n">{counts[w[1]]:,}</span>'
        f'<b>{esc(w[2])}</b> <span class="mute" lang="th">{esc(w[3])}</span><br><span class="small mute">{esc(w[4])}</span></div></a>'
        for w in WALLS)
    lr = math.get("left_vs_right", {})
    ts = math.get("thing_stories", {})
    share = lr.get("share_left_sightings")
    beside = ts.get("thing_pictures_with_him_beside")
    stats = [
        (f"{ts.get('pictures', 0):,}", "pictures on food, drug and recall stories looked at", "ภาพข่าวอาหาร ยา และการเรียกคืน"),
        (f"{ts.get('share_face', 0) or 0:.0%}", "of them carry his face", "มีหน้า RFK"),
        (f"{beside:.0%}" if beside is not None else "—", "of pictures showing the thing put him beside it", "ของที่มี RFK อยู่ข้างๆ"),
        (f"{share:.0%}" if share is not None else "—", "of those put him on the left", "RFK อยู่ซ้าย"),
    ]
    stat_html = "".join(f'<div class="stat"><b>{a}</b><span>{esc(b)} · <span lang="th">{esc(c)}</span></span></div>' for a, b, c in stats)
    body = f"""<h1><small>RFK Jr. · {START} → {dt.date.today().isoformat()}</small>Split Screen
<span class="th" lang="th">ภาพคู่: หน้า RFK กับของที่ถูกกล่าวหา</span></h1>
<p class="lede">His face on the left, a bowl of sugar or a can of soda on the right, a headline about recalls,
poisons and bans underneath. The headline names the thing; his face rides in the picture. The catalog searches the
things, then looks for his face in every picture that comes back.</p>
<p lang="th">หน้า RFK ทางซ้าย น้ำตาลหรือน้ำอัดลมทางขวา พาดหัวข่าวเรื่องเรียกคืน ยาพิษ หรือแบน พาดหัวพูดถึงของ แต่หน้าเขาอยู่ในภาพ ระบบค้นหาจากของ แล้วดูว่ามีหน้าเขาอยู่ในภาพไหน</p>
<div class="stats">{stat_html}</div>
<div class="doors">{doors}</div>
<p class="small mute">Updated {esc(math.get('built', ''))}. A sighting is one post or article showing one picture; a family is
one composite and its recrops, matched by <dfn title="a 64-bit fingerprint of how a picture looks; two copies of one picture land within a few bits">perceptual hash</dfn>.</p>
<p><a href="math/">Math</a> · <a href="data/">Data and method</a></p>"""
    page("index.html", "Split Screen — RFK Jr. beside the thing", "A catalog of split-screen pictures: RFK Jr. on one side, a food or drug on the other, doom headline below.", body)

    for slug, klass, en, th, line in WALLS:
        opts = sorted({x["t"] for x in walls[klass]})
        chips = "".join(f'<button class="chip" data-t="{esc(t)}" aria-pressed="false">{esc(t)} <span lang="th">{esc(THING_TH.get(t, ""))}</span></button>'
                        for t in opts) if klass != "rfk_only" else ""
        years = sorted({x["d"][:4] for x in walls[klass]})
        yopts = "".join(f'<option value="{y}">{y}</option>' for y in years)
        body = f"""<h1><small>{counts[klass]:,} sightings · {pics[klass]:,} pictures</small>{esc(en)}<span class="th" lang="th">{esc(th)}</span></h1>
<p class="lede">{esc(line)}</p>
<div class="bar">
<label>Sort <select id="sort"><option value="d">Newest</option><option value="o">Oldest</option><option value="doom">Doom</option>
<option value="fam">Most reposted</option><option value="e">Most liked</option></select></label>
<label>Year <select id="year"><option value="">All</option>{yopts}</select></label>
<label><input type="checkbox" id="fold" checked> One per picture</label>
<label><input type="search" id="q" placeholder="headline words" aria-label="Search headlines"></label>
<span class="count" id="count"></span></div>
<div class="chips" id="chips">{chips}</div>
<div class="wall" id="wall" aria-live="polite"></div>
<button class="more" id="more" hidden>More</button>
<dialog id="dlg"><button class="x" aria-label="Close">×</button><img alt=""><div class="body"></div></dialog>
<script>{WALL_JS.replace("__SLUG__", slug)}</script>"""
        page(f"{slug}/index.html", f"{en} — Split Screen", line, body, f"{slug}/")

    math_page(math, counts)
    data_page(math)
    (OUT / "icon.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="6" fill="#0b0b0f"/>'
                                  '<rect x="4" y="8" width="12" height="16" fill="#c9b8a6"/><rect x="16" y="8" width="12" height="16" fill="#fff4e0"/>'
                                  '<rect x="4" y="8" width="24" height="16" fill="none" stroke="#ff5a4e" stroke-width="2"/></svg>')
    (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n")
    urls = [""] + [w[0] + "/" for w in WALLS] + ["math/", "data/"]
    (OUT / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                                     + "".join(f"<url><loc>{SITE_URL}/{u}</loc></url>" for u in urls) + "</urlset>")
    shutil.copy(ROOT / "data" / "math.json", OUT / "data" / "math.json") if (ROOT / "data" / "math.json").exists() else None
    print(f"site: {sum(counts.values())} sightings, {len(list((OUT / 'img').glob('*.jpg')))} thumbs")


WALL_JS = r"""
(async()=>{
const all=await (await fetch('../data/__SLUG__.json')).json();
const $=s=>document.querySelector(s);const wall=$('#wall'),more=$('#more'),dlg=$('#dlg');
const on=new Set();let shown=0,list=[];
function hd(a,b){let x=BigInt('0x'+a)^BigInt('0x'+b),n=0;while(x){n+=Number(x&1n);x>>=1n}return n}
// fold sightings into families: same file, or within 8 bits of perceptual hash
const fams=[];const famOf=new Map();
for(const it of all){let f=famOf.get(it.s);
 if(f===undefined){for(let i=0;i<fams.length&&f===undefined;i++){if(hd(fams[i].p,it.p)<=8)f=i}
  if(f===undefined){f=fams.length;fams.push({p:it.p,n:0})}famOf.set(it.s,f)}
 it.f=f;fams[f].n++}
for(const it of all)it.fn=fams[it.f].n;
function apply(){const y=$('#year').value,q=$('#q').value.toLowerCase(),s=$('#sort').value,fold=$('#fold').checked;
 list=all.filter(it=>(!y||it.d.startsWith(y))&&(!on.size||on.has(it.t))&&(!q||it.h.toLowerCase().includes(q)));
 const k={d:(a,b)=>b.d.localeCompare(a.d),o:(a,b)=>a.d.localeCompare(b.d),doom:(a,b)=>b.doom-a.doom,fam:(a,b)=>b.fn-a.fn||b.d.localeCompare(a.d),e:(a,b)=>(b.e||0)-(a.e||0)}[s];
 list.sort(k);
 if(fold){const seen=new Set();list=list.filter(it=>{if(seen.has(it.f))return false;seen.add(it.f);return true})}
 $('#count').textContent=list.length.toLocaleString()+(fold?' pictures':' sightings');
 wall.innerHTML='';shown=0;page()}
function tile(it){const b=document.createElement('button');b.className='tile';
 const pct=Math.min(100,it.doom/3*100);
 b.innerHTML=`<img loading="lazy" src="../img/${it.s}.jpg" alt=""><div class="cap"><div class="meta"><span>${it.d}</span><span>${it.fn>1?`<span class="fam" title="sightings of this picture">×${it.fn}</span> `:''}${esc(it.a||'')}</span></div><div class="h">${esc(it.h)}</div><div class="doom" title="doom ${it.doom}"><i style="width:${pct}%"></i></div></div>`;
 b.onclick=()=>open(it);return b}
function esc(s){return (s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function page(){const f=document.createDocumentFragment();for(const it of list.slice(shown,shown+120))f.appendChild(tile(it));
 wall.appendChild(f);shown+=120;more.hidden=shown>=list.length}
function open(it){dlg.querySelector('img').src=`../img/${it.s}.jpg`;
 const sib=all.filter(x=>x.f===it.f).sort((a,b)=>a.d.localeCompare(b.d));
 dlg.querySelector('.body').innerHTML=`<p><b>${it.d}</b> · ${esc(it.a)} · <a href="${esc(it.u)}" rel="noopener nofollow" target="_blank">source</a></p><p>${esc(it.h)}</p>
 <p class="small mute">thing: ${esc(it.t)} (${it.ts}) · face match ${it.r} · doom ${it.doom}${it.e?` · likes+reposts ${it.e}`:''}</p>
 ${sib.length>1?`<p class="small">${sib.length} sightings of this picture, first ${sib[0].d}:</p><ul class="small">${sib.slice(0,12).map(x=>`<li>${x.d} <a href="${esc(x.u)}" rel="noopener nofollow" target="_blank">${esc(x.a)}</a></li>`).join('')}</ul>`:''}`;
 dlg.showModal()}
dlg.querySelector('.x').onclick=()=>dlg.close();dlg.onclick=e=>{if(e.target===dlg)dlg.close()};
for(const c of document.querySelectorAll('.chip'))c.onclick=()=>{const t=c.dataset.t;on.has(t)?on.delete(t):on.add(t);c.setAttribute('aria-pressed',on.has(t));apply()};
for(const id of ['#sort','#year','#fold'])$(id).onchange=apply;$('#q').oninput=apply;more.onclick=page;apply();
})();
"""


def svg_bars(series, w=900, h=160, color="#ff5a4e", weeks=True):
    """Weekly bars of a daily count series."""
    if weeks:
        series = [sum(series[i:i + 7]) for i in range(0, len(series), 7)]
    n = len(series) or 1
    m = max(series) if series and max(series) > 0 else 1
    bw = w / n
    bars = "".join(f'<rect x="{i * bw:.1f}" y="{h - 18 - v / m * (h - 30):.1f}" width="{max(bw - 1, 1):.1f}" height="{v / m * (h - 30):.1f}" fill="{color}"/>'
                   for i, v in enumerate(series))
    start = dt.date.fromisoformat(START)
    ticks = ""
    for y in range(start.year, dt.date.today().year + 1):
        d = dt.date(y, 1, 1)
        if d < start:
            continue
        x = (d - start).days / 7 * bw
        ticks += f'<line x1="{x:.1f}" x2="{x:.1f}" y1="0" y2="{h - 18}" stroke="#2b2b38"/><text x="{x + 3:.1f}" y="{h - 4}" fill="#aaa497" font-size="11">{y}</text>'
    return f'<svg viewBox="0 0 {w} {h}" role="img">{ticks}{bars}<text x="{w - 4}" y="12" text-anchor="end" fill="#aaa497" font-size="11">max {m}/week</text></svg>'


def svg_bars_months(vals, labels, w=900, h=160, color="#ff5a4e"):
    n = len(vals) or 1
    m = max(vals) if vals and max(vals) > 0 else 1
    bw = w / n
    bars = "".join(f'<rect x="{i * bw:.1f}" y="{h - 18 - v / m * (h - 30):.1f}" width="{max(bw - 2, 1):.1f}" height="{v / m * (h - 30):.1f}" fill="{color}"/>'
                   for i, v in enumerate(vals))
    ticks = "".join(f'<text x="{i * bw + 2:.1f}" y="{h - 4}" fill="#aaa497" font-size="11">{k[:4]}</text>'
                    for i, k in enumerate(labels) if k.endswith("-01") or i == 0)
    return f'<svg viewBox="0 0 {w} {h}" role="img">{ticks}{bars}<text x="{w - 4}" y="12" text-anchor="end" fill="#aaa497" font-size="11">max {m:.1f} per 1,000</text></svg>'


def fmt(x, nd=3):
    if x is None:
        return "—"
    if isinstance(x, float):
        return f"{x:.{nd}g}" if abs(x) < 1e-3 and x != 0 else f"{x:.{nd}f}".rstrip("0").rstrip(".")
    return f"{x:,}" if isinstance(x, int) else str(x)


def math_page(m, counts):
    if not m:
        page("math/index.html", "Math — Split Screen", "The numbers.", "<h1>Math</h1><p>No numbers yet.</p>", "math/")
        return
    lr = m.get("left_vs_right", {})
    cl = m.get("classes", {})
    rows = "".join(
        f"<tr><td>{esc(w[2])} <span lang=th class=mute>{esc(w[3])}</span></td><td class=n>{fmt(cl.get(w[1], {}).get('sightings'))}</td>"
        f"<td class=n>{fmt(cl.get(w[1], {}).get('pictures'))}</td><td class=n>{fmt(cl.get(w[1], {}).get('families'))}</td>"
        f"<td class=n>{fmt(cl.get(w[1], {}).get('doom_mean'))}</td><td class=n>{fmt(cl.get(w[1], {}).get('reuse_gini'))}</td></tr>"
        for w in WALLS)
    daily = m.get("daily", {})
    charts = "".join(f'<h3>{esc(w[2])} <span class="mute" lang="th">{esc(w[3])}</span></h3><div class="chart">{svg_bars(daily.get(w[1], []))}</div>'
                     for w in WALLS if daily.get(w[1]))

    def cps(k):
        segs = (m.get("change_points") or {}).get(k) or []
        return "".join(f"<tr><td>{s['start']}</td><td>{s['end']}</td><td class=n>{fmt(s['rate_per_day'])}</td></tr>" for s in segs)

    hk = m.get("hawkes") or {}
    hk_rows = "".join(f"<tr><td>{esc(w[2])}</td><td class=n>{fmt(hk[w[1]]['branching_ratio'])}</td><td class=n>{fmt(hk[w[1]]['decay_hours'])}</td>"
                      f"<td class=n>{fmt(hk[w[1]]['mu_per_day'])}</td><td class=n>{fmt(hk[w[1]]['n'])}</td></tr>"
                      for w in WALLS if hk.get(w[1]))
    th = m.get("things", {})
    things_rows = ""
    keys = sorted(set(th.get("rfk_left", {})) | set(th.get("rfk_right", {})) | set(th.get("thing_only", {})),
                  key=lambda k: -(th.get("rfk_left", {}).get(k, 0) + th.get("rfk_right", {}).get(k, 0)))
    for k in keys:
        things_rows += (f"<tr><td>{esc(k)} <span lang=th class=mute>{esc(THING_TH.get(k, ''))}</span></td>"
                        + "".join(f"<td class=n>{fmt(th.get(c, {}).get(k, 0))}</td>" for c in ("rfk_left", "rfk_right", "thing_only")) + "</tr>")
    ent = m.get("thing_entropy", {})
    dt_ = m.get("doom_tests", {})
    doom_rows = "".join(f"<tr><td>{esc(k.replace('_vs_rfk_only', ''))}</td><td class=n>{fmt(v['prob_superiority'])}</td><td class=n>{fmt(v['p'])}</td></tr>"
                        for k, v in dt_.items())
    eng = m.get("engagement", {})
    eng_rows = "".join(f"<tr><td>{esc(w[2])}</td><td class=n>{fmt(eng[w[1]]['n'])}</td><td class=n>{fmt(eng[w[1]]['median'])}</td>"
                       f"<td class=n>{esc(str(eng[w[1]]['median_ci']))}</td><td class=n>{fmt(eng[w[1]]['mean'])}</td></tr>"
                       for w in WALLS if eng.get(w[1]))
    pl = {w[1]: cl.get(w[1], {}).get("reuse_powerlaw") for w in WALLS}
    pl_rows = "".join(f"<tr><td>{esc(w[2])}</td><td class=n>{fmt(pl[w[1]]['alpha'])}</td><td class=n>{fmt(pl[w[1]]['xmin'])}</td><td class=n>{fmt(pl[w[1]]['n_tail'])}</td><td class=n>{fmt(pl[w[1]]['ks'])}</td></tr>"
                      for w in WALLS if pl.get(w[1]))
    hod = m.get("hour_of_day_rfk_left") or {}
    xc = (m.get("news_social_xcorr") or {}).get("peak")
    words = m.get("doom_words_split", {})
    ts = m.get("thing_stories") or {}
    mon = ts.get("monthly") or {}
    mon_keys = sorted(mon)
    share_series = [(mon[k]["share_left"] or 0) * 1000 for k in mon_keys]
    outlets = "".join(f"<tr><td>{esc(d)}</td><td class=n>{fmt(v['pictures'])}</td><td class=n>{fmt(v['rfk_left'])}</td><td class=n>{v['share_left']:.1%}</td></tr>"
                      for d, v in list((ts.get("by_outlet") or {}).items())[:25])
    slope = ts.get("left_logit_slope_per_month") or {}
    mon_rows = "".join(f"<tr><td>{k}</td><td class=n>{fmt(mon[k]['pictures'])}</td><td class=n>{fmt(mon[k]['face'])}</td><td class=n>{fmt(mon[k]['rfk_left'])}</td>"
                       f"<td class=n>{(mon[k]['share_left'] or 0):.1%}</td><td class=n>{fmt(mon[k]['thing_alone'])}</td></tr>" for k in mon_keys)
    body = f"""<h1><small>{fmt(m.get('sightings_scored'))} sightings scored</small>Math<span class="th" lang="th">คณิต</span></h1>
<p class="lede">Counts, the left–right split, what sits beside him, how alarmed the headlines read, how the pictures spread.</p>

<h2>Thing stories <span class="th" lang="th">ข่าวของกินของใช้</span></h2>
<p>Pictures on stories found by the thing (outlet slugs, Bluesky term search, GDELT), one count per distinct picture.</p>
<table>
<tr><td>Pictures</td><td class=n>{fmt(ts.get('pictures'))}</td></tr>
<tr><td>With his face (95% Wilson interval)</td><td class=n>{fmt(ts.get('with_his_face'))} = {(ts.get('share_face') or 0):.1%} {esc(str(ts.get('share_face_ci', '')))}</td></tr>
<tr><td>His face left, a thing right</td><td class=n>{fmt(ts.get('rfk_left'))} = {(ts.get('share_left') or 0):.1%} {esc(str(ts.get('share_left_ci', '')))}</td></tr>
<tr><td>His face right, a thing left</td><td class=n>{fmt(ts.get('rfk_right'))}</td></tr>
<tr><td>The thing with no face of his</td><td class=n>{fmt(ts.get('thing_alone'))}</td></tr>
<tr><td>Of pictures showing a thing, share with him beside it</td><td class=n>{(ts.get('thing_pictures_with_him_beside') or 0):.1%} {esc(str(ts.get('thing_pictures_with_him_beside_ci', '')))}</td></tr>
<tr><td>Of those, share with him on the left</td><td class=n>{(ts.get('left_given_face_and_thing') or 0):.1%}</td></tr>
<tr><td>Trend in the RFK-left share, <dfn title="weighted least squares on the log-odds of each month's share; months under 20 pictures left out">odds ratio per year</dfn></td><td class=n>{fmt(slope.get('odds_ratio_per_year'))} (slope {fmt(slope.get('slope'))} ± {fmt(slope.get('se'))} per month)</td></tr>
</table>
<h3>RFK-left share by month, per 1,000 pictures</h3>
<div class="chart">{svg_bars_months(share_series, mon_keys)}</div>
<table><tr><th>month</th><th>pictures</th><th>his face</th><th>RFK left</th><th>share</th><th>thing alone</th></tr>{mon_rows}</table>
<h3>Outlets</h3>
<table><tr><th>outlet</th><th>pictures</th><th>RFK left</th><th>share</th></tr>{outlets}</table>

<h2>Counts <span class="th" lang="th">จำนวน</span></h2>
<table><tr><th></th><th>sightings</th><th>pictures</th><th>families</th><th>doom mean</th><th>reuse Gini</th></tr>{rows}</table>
<p class="small mute"><dfn title="0 = every family posted equally often; 1 = one family takes every sighting">Gini</dfn> measures how unevenly sightings pile onto a few families.</p>

<h2>Left or right <span class="th" lang="th">ซ้ายหรือขวา</span></h2>
<table>
<tr><td>Sightings, RFK left : right</td><td class=n>{fmt(lr.get('sightings', {}).get('left'))} : {fmt(lr.get('sightings', {}).get('right'))}</td></tr>
<tr><td>Share left, sightings (95% Wilson interval)</td><td class=n>{fmt(lr.get('share_left_sightings'))} {esc(str(lr.get('share_left_ci', '')))}</td></tr>
<tr><td>Exact binomial test against 50:50, p</td><td class=n>{fmt(lr.get('binom_p_sightings'))}</td></tr>
<tr><td>Posterior chance the left share exceeds half (flat Beta prior)</td><td class=n>{fmt(lr.get('beta_posterior_p_left_gt_half'))}</td></tr>
<tr><td>Families, RFK left : right</td><td class=n>{fmt(lr.get('families', {}).get('left'))} : {fmt(lr.get('families', {}).get('right'))}</td></tr>
<tr><td>Share left, families (95% interval)</td><td class=n>{fmt(lr.get('share_left_families'))} {esc(str(lr.get('share_left_families_ci', '')))}</td></tr>
<tr><td>Seam position, mean ± sd (0 = left edge, 1 = right)</td><td class=n>{fmt(lr.get('seam_x_mean'))} ± {fmt(lr.get('seam_x_sd'))}</td></tr>
</table>
<p class="small mute">Sightings count reposts; families count each composite once. A gap between the two means a few
left-hand composites got posted many times.</p>

<h2>Beside him <span class="th" lang="th">ของข้างๆ</span></h2>
<table><tr><th>thing</th><th>RFK left</th><th>RFK right</th><th>thing only</th></tr>{things_rows}</table>
<table>
<tr><td><dfn title="Shannon entropy of the thing mix, in bits; 2^bits is the number of equally common kinds it matches">Entropy</dfn>, RFK left</td><td class=n>{fmt((ent.get('rfk_left') or {}).get('bits'))} bits = {fmt((ent.get('rfk_left') or {}).get('effective_kinds'))} kinds</td></tr>
<tr><td>Entropy, RFK right</td><td class=n>{fmt((ent.get('rfk_right') or {}).get('bits'))} bits = {fmt((ent.get('rfk_right') or {}).get('effective_kinds'))} kinds</td></tr>
<tr><td><dfn title="Jensen–Shannon divergence: 0 = same mix, 1 = no overlap">JSD</dfn>, left mix against right mix</td><td class=n>{fmt(m.get('jsd_left_right_things'))}</td></tr>
<tr><td>χ² test, side × thing</td><td class=n>{esc(str(m.get('chi2_side_by_thing', '—')))}</td></tr>
</table>

<h2>Doom <span class="th" lang="th">พาดหัวสยอง</span></h2>
<p>Doom = weighted alarm words (recall, toxic, ban, cancer, autism…) over the square root of the headline's length.
The test below compares each wall with the RFK-only wall: <dfn title="chance a random sighting from this wall reads more alarmed than a random RFK-only sighting; 0.5 = no difference">probability of superiority</dfn> and the Mann–Whitney p.</p>
<table><tr><th>wall</th><th>P(more alarmed)</th><th>p</th></tr>{doom_rows}</table>
<p class="small">Words most often under split screens: {esc(', '.join(f'{k} ({v})' for k, v in list(words.items())[:15]))}</p>
<p class="small">Doom against likes+reposts on Bluesky split screens, Spearman ρ: {esc(str(m.get('doom_vs_engagement_spearman', '—')))}</p>

<h2>Over time <span class="th" lang="th">ตามเวลา</span></h2>
{charts}
<h3>Change points, RFK left</h3>
<p class="small mute">Exact <dfn title="Pruned Exact Linear Time: splits a count series where the daily rate changes, with a Poisson cost and a 2·ln(n) penalty per split">PELT</dfn> on daily counts.</p>
<table><tr><th>from</th><th>to</th><th>per day</th></tr>{cps('rfk_left')}</table>
<h3>Change points, the thing</h3>
<table><tr><th>from</th><th>to</th><th>per day</th></tr>{cps('thing_only')}</table>

<h2>Spread <span class="th" lang="th">การแพร่</span></h2>
<p><dfn title="A self-exciting point process: each sighting raises the chance of another for a while, then the effect decays">Hawkes</dfn> fit on sighting times.
The branching ratio is the share of sightings set off by an earlier one; the decay is how long that push lasts.</p>
<table><tr><th>wall</th><th>branching ratio</th><th>decay, hours</th><th>background per day</th><th>n</th></tr>{hk_rows}</table>
<p>Reposts per family, fitted as a <dfn title="P(size ≥ x) falls like x^(1−α) above x_min; fitted by maximum likelihood, x_min chosen by the smallest Kolmogorov–Smirnov distance (Clauset, Shalizi and Newman 2009)">power law</dfn>:</p>
<table><tr><th>wall</th><th>α</th><th>x_min</th><th>families in tail</th><th>KS</th></tr>{pl_rows}</table>
<p class="small">Hour of day, RFK left (Rayleigh test for a preferred hour): peak {fmt(hod.get('peak_hour_utc'))} UTC, R = {fmt(hod.get('R'))}, p = {fmt(hod.get('p'))}, n = {fmt(hod.get('n'))}.</p>
<p class="small">News against Bluesky, daily cross-correlation peak: {esc(str(xc)) if xc else '—'} (lag in days; positive = news first).</p>
"""
    page("math/index.html", "Math — Split Screen", "Left against right, what sits beside him, doom, spread.", body, "math/")


def data_page(m):
    body = f"""<h1>Data<span class="th" lang="th">ข้อมูล</span></h1>
<p>Each wall's rows: <a href="left.json">left.json</a> · <a href="right.json">right.json</a> · <a href="thing.json">thing.json</a> ·
<a href="face.json">face.json</a> · the math: <a href="math.json">math.json</a>.</p>
<p>Fields: <code>s</code> picture sha1 · <code>d</code> date · <code>u</code> source · <code>a</code> account or site ·
<code>h</code> headline or post text · <code>t</code> thing label · <code>ts</code> share of CLIP mass on thing labels ·
<code>r</code> face match to RFK Jr. · <code>doom</code> · <code>e</code> likes+reposts+quotes (Bluesky) · <code>p</code> perceptual hash.</p>
<h2>Method <span class="th" lang="th">วิธี</span></h2>
<ol>
<li><b>Find.</b> The things, not his name: outlets' own sitemaps (every article, its date and lead picture) filtered to slugs
naming sugar, soda, dyes, recalls, the FDA, vaccines, Tylenol, fluoride and the rest; Bluesky search, day by day, for the same
words, every attached picture and link-card picture; GDELT (a free index of world online news) for articles mentioning him.
A first pass searched Bluesky by his name; those rows stay in the walls and out of the thing-story shares.</li>
<li><b>Face.</b> OpenCV's YuNet finds faces; SFace turns each into 128 numbers; a face counts as his when its mean cosine
similarity to his five nearest reference faces, taken from Wikimedia Commons photographs, clears the threshold.</li>
<li><b>Side.</b> His face left of the picture's centre files it left; right of centre, right.</li>
<li><b>Thing.</b> CLIP (ViT-B/32, trained on LAION-2B captioned images) scores the part of the picture beyond his face against 180-odd written
labels (sugar, soda, food dye, Tylenol, vaccines… and scene labels like podium, crowd, tweet screenshot); a thing counts when thing labels
take at least half the mass and the best one clears a cosine of 0.24.</li>
<li><b>Seam.</b> A straight vertical cut, where one exists, is recorded; it does not decide the class.</li>
<li><b>Doom.</b> A weighted word list over the headline or post text.</li>
</ol>
<p>Misses and false matches both happen: a face turned away, a composite with no hard seam, a plate of food CLIP calls a podium.
Scores ship with every row so a reader can set a stricter cut.</p>
<p class="small mute">Window {START} to {esc((m.get('window') or ['', ''])[1])}. Built {esc(m.get('built', ''))}.</p>"""
    page("data/index.html", "Data — Split Screen", "Rows, fields and method.", body, "data/")


if __name__ == "__main__":
    main()
