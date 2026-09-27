"""Render content/dossier.json into site/index.html (no external dependencies)."""
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content" / "dossier.json"
OUT_DIR = ROOT / "site"
CSS = (ROOT / "scripts" / "style.css").read_text(encoding="utf-8")
STATIC = {"pipeline": (ROOT / "scripts" / "pipeline.svg").read_text(encoding="utf-8")}

LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
REF = re.compile(r"\s*\[\[(s\d+[a-z]?)\]\]")
I18N = ROOT / "content" / "i18n"
UI_ALL = json.loads((I18N / "ui.json").read_text(encoding="utf-8"))
LANGS = ["fr", "en", "es", "de", "it"]
U = UI_ALL["fr"]
LANG = "fr"
BASE_URL = "https://s-ops-tool.github.io/ai-radar/"
DEC = re.compile(r"(?<=\d),(?=\d)")
SKIP_KEYS = {"id", "type", "auto", "vendor", "key", "url", "src", "date", "for", "name", "kind", "prefix",
             "src_ref", "handles", "names", "include", "exclude", "queries", "keywords", "updated", "display",
             "model", "m", "textonly", "band", "migrations"}


def set_lang(lang):
    global U, LANG
    LANG, U = lang, UI_ALL[lang]


def num(x, d=None):
    s = str(x) if d is None else f"{x:.{d}f}"
    return s if U["decimal"] == "." else s.replace(".", ",")


def loc_display(s):
    return DEC.sub(".", s) if U["decimal"] == "." else s


def fr_date(iso):
    y, m, d = iso.split("-")
    return U["date_fmt"].format(d=int(d), m=U["months"][int(m) - 1], y=y)


def translate_tree(obj, table, key=None):
    """Replace every translatable string by its translation (falls back to French)."""
    if isinstance(obj, str):
        if key in SKIP_KEYS:
            return obj
        return table.get(obj, obj)
    if isinstance(obj, list):
        if key == "sections" and all(isinstance(x, str) for x in obj):
            return obj
        return [translate_tree(x, table, key) for x in obj]
    if isinstance(obj, dict):
        return {k: translate_tree(v, table, k) for k, v in obj.items()}
    return obj


def src_num(sid):
    return re.sub(r"\D", "", sid) or sid


def txt(s, sources):
    """Escape text, then turn [[sN]] markers into superscript links."""
    out = html.escape(s, quote=False)

    def rep(m):
        sid = m.group(1)
        if sid not in sources:
            return ""
        return f'<sup><a href="#{sid}">{src_num(sid)}</a></sup>'

    out = REF.sub(rep, out)
    return LINK.sub(lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', out)


def band_html(band):
    if band is None:
        return '<div class="band nd"><i></i><i></i><i></i><i></i><i></i></div>'
    return f'<div class="band b{int(band)}"><i></i><i></i><i></i><i></i><i></i></div>'


def render_matrix(d):
    vendors = d["vendors"]
    head = "".join(
        f'<th scope="col"><span class="sw" style="background:var(--{v["id"]})"></span>{html.escape(v["name"])}</th>'
        for v in vendors)
    rows = []
    for row in d["matrix"]:
        cells = []
        for v in vendors:
            c = row["cells"].get(v["id"], {"band": None, "text": U["nd"]})
            if c.get("textonly"):
                cells.append(f'<td class="cell">{html.escape(c["text"])}</td>')
            else:
                cells.append(f'<td>{band_html(c.get("band"))}<div class="cell">{html.escape(c["text"])}</div></td>')
        rows.append(f'<tr><th scope="row">{html.escape(row["label"])}</th>{"".join(cells)}</tr>')
    return (
        f'<section id="matrice"><h2>{U["matrix_title"]}</h2><p>{html.escape(U["matrix_intro"])}</p>'
        f'<div class="scroll"><table class="matrix"><thead><tr><th scope="col">{U["dimension"]}</th>{head}</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div></section>')


def render_bar_chart(b, sources):
    x0, x1 = 190, 610
    mx = float(b["max"])
    scale = (x1 - x0) / mx
    bars = b["bars"]
    top = 30
    step = 44
    bottom = top + step * len(bars)
    h = bottom + 40
    parts = [f'<svg viewBox="0 0 640 {h}" role="img" aria-label="{html.escape(b["title"])}">']
    ticks = b.get("ticks", [0, mx])
    labels = b.get("ticklabels") or [num(f"{t:g}") for t in ticks]
    parts.append('<g class="grid">')
    for t in ticks:
        x = x0 + t * scale
        parts.append(f'<line x1="{x:.1f}" y1="{top - 10}" x2="{x:.1f}" y2="{bottom}"/>')
    parts.append('</g><g font-size="12" text-anchor="middle">')
    for t, lab in zip(ticks, labels):
        x = x0 + t * scale
        parts.append(f'<text x="{x:.1f}" y="{bottom + 20}" class="muted">{html.escape(str(lab))}</text>')
    parts.append("</g>")
    for i, bar in enumerate(bars):
        y = top + i * step
        w = max(1.0, bar["value"] * scale)
        cls = "f-" + bar.get("vendor", "ms")
        parts.append(f'<text x="0" y="{y + 12}" font-size="13" font-weight="600">{html.escape(bar["label"])}</text>')
        if bar.get("sublabel"):
            parts.append(f'<text x="0" y="{y + 27}" font-size="11" class="muted">{html.escape(bar["sublabel"])}</text>')
        parts.append(f'<rect x="{x0}" y="{y}" width="{w:.1f}" height="22" class="{cls}"/>')
        parts.append(f'<text x="{x0 + w + 6:.1f}" y="{y + 16}" font-size="12">{html.escape(loc_display(bar.get("display", str(bar["value"]))))}</text>')
    ref = b.get("refline")
    if ref:
        x = x0 + ref["value"] * scale
        parts.append(f'<line x1="{x:.1f}" y1="{top - 14}" x2="{x:.1f}" y2="{bottom}" stroke="var(--warn)" stroke-width="1.5" stroke-dasharray="4 3"/>')
        parts.append(f'<text x="{x - 4:.1f}" y="{top - 18}" font-size="11" text-anchor="end" style="fill:var(--warn)">{html.escape(ref["label"])}</text>')
    parts.append("</svg>")
    cap = f'<figcaption>{txt(b["caption"], sources)}</figcaption>' if b.get("caption") else ""
    return (f'<figure class="chart"><h4>{html.escape(b["title"])}</h4>'
            f'<div class="scroll" style="margin:0">{"".join(parts)}</div>{cap}</figure>')


def short_date(x):
    if not x:
        return U["date_unverified"]
    parts = x.split("-")
    return f"{U['months_short'][int(parts[1]) - 1]} {parts[0]}"


def render_dot_chart(b, sources):
    x0, x1 = 120, 430
    mx = float(b["max"])
    sc = (x1 - x0) / mx
    rows = b.get("rows", [])
    top, step = 40, 62
    h = top + step * len(rows) + 30
    out = [f'<svg viewBox="0 0 660 {h}" role="img" aria-label="{html.escape(b["title"])}">']
    out.append('<g class="grid">')
    for t in b["ticks"]:
        x = x0 + t * sc
        out.append(f'<line x1="{x:.1f}" y1="{top - 16}" x2="{x:.1f}" y2="{top + step * len(rows) - 20}"/>')
    out.append('</g><g font-size="12" text-anchor="middle">')
    for t in b["ticks"]:
        out.append(f'<text x="{x0 + t * sc:.1f}" y="{top + step * len(rows)}" class="muted">{t}</text>')
    out.append("</g>")
    out.append(f'<text x="455" y="{top - 22}" font-size="11" font-weight="600">{html.escape(U["dot_latest"])}</text>')
    for i, r in enumerate(rows):
        y = top + i * step
        v = r["vendor"]
        out.append(f'<text x="0" y="{y + 4}" font-size="13" font-weight="600">{html.escape(r["label"])}</text>')
        out.append(f'<line x1="{x0}" y1="{y}" x2="{x1}" y2="{y}" class="axis"/>')
        for dtt in r["dots"]:
            out.append(f'<circle cx="{x0 + dtt["value"] * sc:.1f}" cy="{y}" r="4" fill="var(--ink2)" opacity=".35">'
                       f'<title>{html.escape(dtt["model"])} : {num(dtt["value"])} %</title></circle>')
        t = r["tested"]
        if t.get("value") is not None:
            cx = x0 + t["value"] * sc
            out.append(f'<circle cx="{cx:.1f}" cy="{y}" r="7" class="f-{v}"/>')
            lab = f'{t["label"]}, {num(t["value"])} % ({short_date(t.get("date"))})'
            anchor = "end" if cx > x0 + 0.3 * (x1 - x0) else "start"
            tx = cx - 10 if anchor == "end" else cx + 10
            out.append(f'<text x="{tx:.1f}" y="{y + 20}" font-size="11" text-anchor="{anchor}">{html.escape(lab)}</text>')
        lt = r["latest"]
        out.append(f'<text x="455" y="{y - 2}" font-size="12">{html.escape(lt["label"])} ({short_date(lt.get("date"))})</text>')
        if lt.get("evaluated"):
            out.append(f'<text x="455" y="{y + 14}" font-size="11" class="muted">{html.escape(U["dot_evaluated"])}</text>')
        else:
            gap = r.get("gap_months")
            w = 0 if gap is None else min(gap, 12) / 12 * 160
            out.append(f'<rect x="455" y="{y + 6}" width="160" height="7" fill="var(--faint)"/>')
            if gap is not None:
                out.append(f'<rect x="455" y="{y + 6}" width="{w:.1f}" height="7" fill="var(--warn)"/>')
            msg = U["dot_not_evaluated"] + ", " + (U["dot_gap"].format(n=gap) if gap is not None else U["dot_gap_unknown"])
            out.append(f'<text x="455" y="{y + 28}" font-size="11" class="muted">{html.escape(msg)}</text>')
    out.append("</svg>")
    cap = f'<figcaption>{txt(b["caption"], sources)}</figcaption>' if b.get("caption") else ""
    return (f'<figure class="chart"><h4>{html.escape(b["title"])}</h4>'
            f'<div class="scroll" style="margin:0">{"".join(out)}</div>{cap}</figure>')


def render_line_chart(b, sources):
    if not b.get("points"):
        cap = f'<figcaption>{txt(b.get("caption") or "", sources)}</figcaption>' if b.get("caption") else ""
        return f'<figure class="chart"><h4>{html.escape(b["title"])}</h4>{cap}</figure>'
    x0, x1, y0, y1 = 70, 560, 250, 30
    months = [pt["m"] for pt in b["points"]]
    mmin, mmax = min(months), max(months)
    ymax = float(b["max"])
    X = lambda m: x0 + (m - mmin) / ((mmax - mmin) or 1) * (x1 - x0)
    Y = lambda v: y0 - v / ymax * (y0 - y1)
    out = [f'<svg viewBox="0 0 680 290" role="img" aria-label="{html.escape(b["title"])}"><g class="grid">']
    for t in b["ticks"]:
        out.append(f'<line x1="{x0}" y1="{Y(t):.1f}" x2="{x1}" y2="{Y(t):.1f}"/>')
    out.append('</g><g font-size="12" class="muted">')
    for t in b["ticks"]:
        out.append(f'<text x="{x0 - 10}" y="{Y(t) + 4:.1f}" text-anchor="end" class="muted">{t}</text>')
    for pt in b["points"]:
        out.append(f'<text x="{X(pt["m"]):.1f}" y="{y0 + 22}" text-anchor="middle" class="muted">{html.escape(pt["label"])}</text>')
    out.append("</g>")
    ends = []
    for se in b["series"]:
        vals = [(pt["m"], pt["values"].get(se["key"])) for pt in b["points"] if pt["values"].get(se["key"]) is not None]
        if not vals:
            continue
        d = " ".join(f'{"M" if i == 0 else "L"}{X(m):.1f},{Y(v):.1f}' for i, (m, v) in enumerate(vals))
        color = f'var(--{se["vendor"]})'
        out.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2.5"/>')
        for m, v in vals:
            out.append(f'<circle cx="{X(m):.1f}" cy="{Y(v):.1f}" r="3.5" fill="{color}"><title>{html.escape(se["label"])} : {num(v)} %</title></circle>')
        ends.append([Y(vals[-1][1]), se["label"], vals[-1][1], color])
    ends.sort()
    last = -99
    for e in ends:
        e[0] = max(e[0], last + 15)
        last = e[0]
        out.append(f'<text x="{x1 + 12}" y="{e[0] + 4:.1f}" font-size="12" style="fill:{e[3]}">{html.escape(e[1])} {num(e[2])}</text>')
    out.append("</svg>")
    cap = f'<figcaption>{txt(b["caption"], sources)}</figcaption>' if b.get("caption") else ""
    return (f'<figure class="chart"><h4>{html.escape(b["title"])}</h4>'
            f'<div class="scroll" style="margin:0">{"".join(out)}</div>{cap}</figure>')


def render_block(b, sources):
    t = b["type"]
    if t == "para":
        return f"<p>{txt(b['text'], sources)}</p>"
    if t == "subhead":
        return f"<h4>{html.escape(b['text'])}</h4>"
    if t == "why":
        return f'<p class="why">{txt(b["text"], sources)}</p>'
    if t == "audiences":
        labels = [(k, U["aud_" + k]) for k in ("public", "entreprises", "institutions")]
        return '<div class="aud">' + "".join(
            f'<div class="a-{k}"><strong>{n}</strong>{txt(b.get(k, ""), sources)}</div>' for k, n in labels) + "</div>"
    if t == "details":
        inner = "".join(render_block(x, sources) for x in b["blocks"])
        return f'<details class="deep"><summary>{html.escape(b["summary"])}</summary><div class="inner">{inner}</div></details>'
    if t == "reading":
        return f'<div class="reading"><p><strong>{U["reading"]}</strong> {txt(b["text"], sources)}</p></div>'
    if t == "list":
        return "<ul>" + "".join(f"<li>{txt(i, sources)}</li>" for i in b["items"]) + "</ul>"
    if t == "table":
        head = "".join(f"<th>{html.escape(h)}</th>" for h in b["headers"])
        body = "".join("<tr>" + "".join(f"<td>{txt(c, sources)}</td>" for c in r) + "</tr>" for r in b["rows"])
        return (f'<div class="scroll"><table class="plain" style="min-width:680px">'
                f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>")
    if t == "timeline":
        items = "".join(f"<li><time>{html.escape(i['date'])}</time>{txt(i['text'], sources)}</li>" for i in b["items"])
        return f'<ol class="timeline">{items}</ol>'
    if t == "bar_chart":
        return render_bar_chart(b, sources)
    if t == "line_chart":
        return render_line_chart(b, sources)
    if t == "dot_chart":
        return render_dot_chart(b, sources)
    if t == "static":
        svg = STATIC.get(b["name"], "")
        for fr_t, tr in U.get("pipeline", {}).items():
            svg = svg.replace(">" + fr_t + "<", ">" + html.escape(tr, quote=False) + "<")
        cap = f'<figcaption>{txt(b["caption"], sources)}</figcaption>' if b.get("caption") else ""
        return f'<figure class="chart"><div class="scroll" style="margin:0">{svg}</div>{cap}</figure>'
    return ""


def render_section(s, sources):
    tags = "".join(f'<span class="tag">{U["aud_" + a]}</span>' for a in s.get("for", []) if "aud_" + a in U)
    body = "".join(render_block(b, sources) for b in s["blocks"])
    watch = (f'<p class="watch">{U["watch"]} {html.escape(", ".join(s["watch"]))}.</p>'
             if s.get("watch") else "")
    return (f'<section class="sec" id="{s["id"]}" data-for="{" ".join(s.get("for", []))}">'
            f'<h3>{html.escape(s["title"])}</h3><div class="tags">{tags}</div>{body}{watch}</section>')


def lang_prefix(target):
    """Relative link from the current language page to the target language page."""
    up = "" if LANG == "fr" else "../"
    return up + ("" if target == "fr" else target + "/")


def render(d):
    sources = d["sources"]
    meta = d["meta"]
    secs = {s["id"]: s for s in d["sections"]}
    parts = d.get("parts") or [{"id": "dossier", "title": "Dossier", "intro": "", "sections": list(secs)}]
    placed = {sid for p in parts for sid in p["sections"]}
    orphans = [sid for sid in secs if sid not in placed]
    if orphans:
        parts = parts + [{"id": "autres", "title": "+", "intro": "", "sections": orphans}]

    toc = [f'<div class="tg"><span class="grp">{U["toc_synth"]}</span><a href="#bref">{U["brief"]}</a><a href="#matrice">{U["matrix"]}</a></div>']
    for p in parts:
        links = "".join(f'<a href="#{sid}" data-sec="{sid}">{html.escape(secs[sid]["title"].split(":")[0].strip())}</a>'
                        for sid in p["sections"] if sid in secs)
        toc.append(f'<div class="tg"><span class="grp">{html.escape(p["title"])}</span>{links}</div>')
    toc.append(f'<div class="tg"><span class="grp">{U["toc_refs"]}</span><a href="#glossaire">{U["glossary"]}</a>'
               f'<a href="#journal">{U["journal"]}</a><a href="#angles">{U["blind"]}</a><a href="#sources">{U["sources"]}</a></div>')
    switch = "".join(
        (f'<span aria-current="page">{l.upper()}</span>' if l == LANG else
         f'<a href="{lang_prefix(l)}" hreflang="{l}" lang="{l}" title="{UI_ALL[l]["lang_name"]}">{l.upper()}</a>')
        for l in LANGS)
    alternates = "".join(f'<link rel="alternate" hreflang="{l}" href="{BASE_URL}{"" if l == "fr" else l + "/"}">' for l in LANGS)

    brief = "".join(f"<li>{txt(k, sources)}</li>" for k in d.get("keypoints", []))
    profiles = "".join(
        f'<button type="button" class="profile" data-id="{p["id"]}" aria-pressed="false">'
        f'<b>{html.escape(p["name"])}</b><span>{html.escape(p["questions"])}</span></button>'
        for p in d.get("profiles", []))

    parts_html = ""
    for p in parts:
        inner = "".join(render_section(secs[sid], sources) for sid in p["sections"] if sid in secs)
        intro = f'<p class="part-intro">{html.escape(p["intro"])}</p>' if p.get("intro") else ""
        parts_html += f'<div class="part" id="part-{p["id"]}"><h2>{html.escape(p["title"])}</h2>{intro}{inner}</div>'

    gloss = "".join(f"<dt>{html.escape(t)}</dt><dd>{html.escape(x)}</dd>" for t, x in d.get("glossary", []))
    log = "".join(
        f"<li><time>{fr_date(c['date'])}</time><ul>" + "".join(f"<li>{txt(i, sources)}</li>" for i in c["items"]) + "</ul></li>"
        for c in sorted(d["changelog"], key=lambda c: c["date"], reverse=True)[:12])
    blind = "".join(f"<li>{html.escape(b)}</li>" for b in d["blind_spots"])
    srcs = "".join(
        f'<li id="{sid}"><span class="num">{src_num(sid)}.</span> <a href="{html.escape(s["url"])}">{html.escape(s["title"])}</a></li>'
        for sid, s in sorted(sources.items(), key=lambda kv: int(src_num(kv[0]) or 0)))

    return f"""<!DOCTYPE html>
<html lang="{LANG}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{html.escape(meta["title"])}</title>
<meta name="description" content="{html.escape(meta["lede"])}">
{alternates}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Condensed:wght@500;600;700&family=IBM+Plex+Sans:ital,wght@0,400;0,500;0,600;1,400&display=swap" rel="stylesheet">
<style>{CSS}
ol.log{{list-style:none;padding:0;max-width:76ch}}
ol.log>li{{margin-bottom:14px}}
.watch{{font-size:.85rem;color:var(--ink2);margin-top:18px;max-width:76ch}}
.sources{{list-style:none}}
.langs{{display:flex;gap:10px;font-size:.85rem;margin-top:10px}}
.langs span{{font-weight:700}}
.langs a{{text-decoration:none;color:var(--ink2)}}
.langs a:hover{{color:var(--accent)}}
.sources .num{{display:inline-block;min-width:2.2em;font-variant-numeric:tabular-nums}}
ol.log time{{font-family:"IBM Plex Sans Condensed","Arial Narrow",sans-serif;font-weight:600}}
</style>
</head>
<body>
<button class="themebtn" id="themebtn" type="button">{U["theme"]}</button>
<div class="wrap">
<header class="top">
<h1>{html.escape(meta["title"])}</h1>
<p class="lede">{html.escape(meta["lede"])}</p>
<p class="meta">{U["updated"]} {fr_date(meta["updated"])}. {html.escape(meta["note"])}</p>
<nav class="langs" aria-label="{U["languages"]}">{switch}</nav>
<nav class="toc" aria-label="{U["toc_synth"]}">{"".join(toc)}</nav>
</header>
<section id="bref"><h2>{U["brief"]}</h2><ol class="brief">{brief}</ol>
<h4>{U["read_by_profile"]}</h4>
<div class="profiles">{profiles}</div>
<p class="filterstate" id="filterstate" aria-live="polite"></p>
</section>
{render_matrix(d)}
{parts_html}
<section id="glossaire"><h2>{U["glossary"]}</h2><dl class="gloss">{gloss}</dl></section>
<section id="journal"><h2>{U["journal_title"]}</h2><ol class="log">{log}</ol></section>
<section id="angles"><h2>{U["blind_title"]}</h2><ul>{blind}</ul></section>
<section id="sources"><h2>{U["sources"]}</h2><ul class="sources">{srcs}</ul></section>
</div>
<script>
(function(){{
  var root=document.documentElement,body=document.body,saved=null;
  try{{saved=localStorage.getItem('theme');}}catch(e){{}}
  if(saved==='light'||saved==='dark'){{root.setAttribute('data-theme',saved);}}
  document.getElementById('themebtn').addEventListener('click',function(){{
    var cur=root.getAttribute('data-theme');
    if(!cur){{cur=window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';}}
    var next=cur==='dark'?'light':'dark';
    root.setAttribute('data-theme',next);
    try{{localStorage.setItem('theme',next);}}catch(e){{}}
  }});
  var names={json.dumps({k: U["aud_" + k] for k in ("public", "entreprises", "institutions")}, ensure_ascii=False)};
  var FSTATE={json.dumps(U["filter_state"], ensure_ascii=False)}, SHOWALL={json.dumps(U["show_all"], ensure_ascii=False)};
  var btns=[].slice.call(document.querySelectorAll('.profile'));
  var state=document.getElementById('filterstate');
  function apply(aud){{
    if(aud){{body.setAttribute('data-aud',aud);}}else{{body.removeAttribute('data-aud');}}
    btns.forEach(function(b){{b.setAttribute('aria-pressed',b.dataset.id===aud?'true':'false');}});
    var hidden=0;
    [].slice.call(document.querySelectorAll('section.sec')).forEach(function(s){{
      var show=!aud||(' '+s.dataset.for+' ').indexOf(' '+aud+' ')>=0;
      if(!show){{hidden++;}}
      var link=document.querySelector('nav.toc a[data-sec="'+s.id+'"]');
      if(link){{link.style.display=show?'':'none';}}
    }});
    [].slice.call(document.querySelectorAll('.part')).forEach(function(p){{
      var any=[].slice.call(p.querySelectorAll('section.sec')).some(function(s){{return getComputedStyle(s).display!=='none';}});
      p.style.display=any?'':'none';
    }});
    if(aud){{
      state.textContent=FSTATE.replace('{{name}}',names[aud]).replace('{{n}}',hidden)+' ';
      var sb=document.createElement('button');sb.type='button';sb.id='showall';sb.textContent=SHOWALL;state.appendChild(sb);
      document.getElementById('showall').addEventListener('click',function(){{apply(null);}});
    }}else{{state.textContent='';}}
    try{{if(aud){{localStorage.setItem('aud',aud);}}else{{localStorage.removeItem('aud');}}}}catch(e){{}}
  }}
  btns.forEach(function(b){{b.addEventListener('click',function(){{
    apply(body.getAttribute('data-aud')===b.dataset.id?null:b.dataset.id);
  }});}});
  var a=null;try{{a=localStorage.getItem('aud');}}catch(e){{}}
  if(a&&names[a]){{apply(a);}}
}})();
</script>
</body>
</html>
"""


def load_table(lang):
    path = I18N / f"{lang}.json"
    if lang == "fr" or not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {e["fr"]: e["tr"] for e in data.values() if e.get("tr")}


def main():
    d = json.loads(CONTENT.read_text(encoding="utf-8"))
    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / ".nojekyll").write_text("", encoding="utf-8")
    for lang in LANGS:
        set_lang(lang)
        table = load_table(lang)
        doc = translate_tree(d, table) if table else d
        out = OUT_DIR if lang == "fr" else OUT_DIR / lang
        out.mkdir(parents=True, exist_ok=True)
        (out / "index.html").write_text(render(doc), encoding="utf-8")
        print(f"{lang} : {len(table)} traductions disponibles")
    set_lang("fr")
    print(f"site écrit en {len(LANGS)} langues ({len(d['sources'])} sources, {len(d['sections'])} sections)")


if __name__ == "__main__":
    main()
