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

REF = re.compile(r"\s*\[\[(s\d+[a-z]?)\]\]")
MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
          "août", "septembre", "octobre", "novembre", "décembre"]


def fr_date(iso):
    y, m, d = iso.split("-")
    return f"{int(d)} {MONTHS[int(m) - 1]} {y}"


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

    return REF.sub(rep, out)


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
            c = row["cells"].get(v["id"], {"band": None, "text": "n.d."})
            if c.get("textonly"):
                cells.append(f'<td class="cell">{html.escape(c["text"])}</td>')
            else:
                cells.append(f'<td>{band_html(c.get("band"))}<div class="cell">{html.escape(c["text"])}</div></td>')
        rows.append(f'<tr><th scope="row">{html.escape(row["label"])}</th>{"".join(cells)}</tr>')
    return (
        '<section id="matrice"><h2>Matrice de lecture</h2>'
        "<p>Les bandes indiquent un niveau relatif entre les six acteurs, établi à partir des sources citées plus bas. "
        "Une bande en pointillés signale une absence de donnée publique : elle ne vaut pas un score faible.</p>"
        f'<div class="scroll"><table class="matrix"><thead><tr><th scope="col">Dimension</th>{head}</tr></thead>'
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
    labels = b.get("ticklabels") or [f"{t:g}".replace(".", ",") for t in ticks]
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
        parts.append(f'<text x="{x0 + w + 6:.1f}" y="{y + 16}" font-size="12">{html.escape(bar.get("display", str(bar["value"])))}</text>')
    ref = b.get("refline")
    if ref:
        x = x0 + ref["value"] * scale
        parts.append(f'<line x1="{x:.1f}" y1="{top - 14}" x2="{x:.1f}" y2="{bottom}" stroke="var(--warn)" stroke-width="1.5" stroke-dasharray="4 3"/>')
        parts.append(f'<text x="{x - 4:.1f}" y="{top - 18}" font-size="11" text-anchor="end" style="fill:var(--warn)">{html.escape(ref["label"])}</text>')
    parts.append("</svg>")
    cap = f'<figcaption>{txt(b["caption"], sources)}</figcaption>' if b.get("caption") else ""
    return (f'<figure class="chart"><h4>{html.escape(b["title"])}</h4>'
            f'<div class="scroll" style="margin:0">{"".join(parts)}</div>{cap}</figure>')


MONTHS_SHORT = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]


def short_date(x):
    if not x:
        return "date non vérifiée"
    parts = x.split("-")
    return f"{MONTHS_SHORT[int(parts[1]) - 1]} {parts[0]}"


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
    out.append(f'<text x="455" y="{top - 22}" font-size="11" font-weight="600">Dernier modèle phare de l\'éditeur</text>')
    for i, r in enumerate(rows):
        y = top + i * step
        v = r["vendor"]
        out.append(f'<text x="0" y="{y + 4}" font-size="13" font-weight="600">{html.escape(r["label"])}</text>')
        out.append(f'<line x1="{x0}" y1="{y}" x2="{x1}" y2="{y}" class="axis"/>')
        for dtt in r["dots"]:
            out.append(f'<circle cx="{x0 + dtt["value"] * sc:.1f}" cy="{y}" r="4" fill="var(--ink2)" opacity=".35">'
                       f'<title>{html.escape(dtt["model"])} : {str(dtt["value"]).replace(".", ",")} %</title></circle>')
        t = r["tested"]
        if t.get("value") is not None:
            cx = x0 + t["value"] * sc
            out.append(f'<circle cx="{cx:.1f}" cy="{y}" r="7" class="f-{v}"/>')
            lab = f'{t["label"]}, {str(t["value"]).replace(".", ",")} % ({short_date(t.get("date"))})'
            anchor = "end" if cx > x0 + 0.3 * (x1 - x0) else "start"
            tx = cx - 10 if anchor == "end" else cx + 10
            out.append(f'<text x="{tx:.1f}" y="{y + 20}" font-size="11" text-anchor="{anchor}">{html.escape(lab)}</text>')
        lt = r["latest"]
        out.append(f'<text x="455" y="{y - 2}" font-size="12">{html.escape(lt["label"])} ({short_date(lt.get("date"))})</text>')
        if lt.get("evaluated"):
            out.append(f'<text x="455" y="{y + 14}" font-size="11" class="muted">Évalué ci-contre</text>')
        else:
            gap = r.get("gap_months")
            w = 0 if gap is None else min(gap, 12) / 12 * 160
            out.append(f'<rect x="455" y="{y + 6}" width="160" height="7" fill="var(--faint)"/>')
            if gap is not None:
                out.append(f'<rect x="455" y="{y + 6}" width="{w:.1f}" height="7" fill="var(--warn)"/>')
            msg = "non évalué" + (f", {gap} mois d'écart" if gap is not None else ", écart inconnu")
            out.append(f'<text x="455" y="{y + 28}" font-size="11" class="muted">{html.escape(msg)}</text>')
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
        labels = [("public", "Grand public"), ("entreprises", "Entreprises"), ("institutions", "Institutions")]
        return '<div class="aud">' + "".join(
            f'<div class="a-{k}"><strong>{n}</strong>{txt(b.get(k, ""), sources)}</div>' for k, n in labels) + "</div>"
    if t == "details":
        inner = "".join(render_block(x, sources) for x in b["blocks"])
        return f'<details class="deep"><summary>{html.escape(b["summary"])}</summary><div class="inner">{inner}</div></details>'
    if t == "reading":
        return f'<div class="reading"><p><strong>Lecture.</strong> {txt(b["text"], sources)}</p></div>'
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
    if t == "dot_chart":
        return render_dot_chart(b, sources)
    if t == "static":
        svg = STATIC.get(b["name"], "")
        cap = f'<figcaption>{txt(b["caption"], sources)}</figcaption>' if b.get("caption") else ""
        return f'<figure class="chart"><div class="scroll" style="margin:0">{svg}</div>{cap}</figure>'
    return ""


AUD_NAMES = {"public": "Grand public", "entreprises": "Entreprises", "institutions": "Institutions"}


def render_section(s, sources):
    tags = "".join(f'<span class="tag">{AUD_NAMES[a]}</span>' for a in s.get("for", []) if a in AUD_NAMES)
    body = "".join(render_block(b, sources) for b in s["blocks"])
    watch = (f'<p class="watch">Sources suivies chaque semaine : {html.escape(", ".join(s["watch"]))}.</p>'
             if s.get("watch") else "")
    return (f'<section class="sec" id="{s["id"]}" data-for="{" ".join(s.get("for", []))}">'
            f'<h3>{html.escape(s["title"])}</h3><div class="tags">{tags}</div>{body}{watch}</section>')


def render(d):
    sources = d["sources"]
    meta = d["meta"]
    secs = {s["id"]: s for s in d["sections"]}
    parts = d.get("parts") or [{"id": "dossier", "title": "Dossier", "intro": "", "sections": list(secs)}]
    placed = {sid for p in parts for sid in p["sections"]}
    orphans = [sid for sid in secs if sid not in placed]
    if orphans:
        parts = parts + [{"id": "autres", "title": "Autres sujets", "intro": "", "sections": orphans}]

    toc = ['<div class="tg"><span class="grp">Synthèse</span><a href="#bref">En bref</a><a href="#matrice">Matrice</a></div>']
    for p in parts:
        links = "".join(f'<a href="#{sid}" data-sec="{sid}">{html.escape(secs[sid]["title"].split(" :")[0])}</a>'
                        for sid in p["sections"] if sid in secs)
        toc.append(f'<div class="tg"><span class="grp">{html.escape(p["title"])}</span>{links}</div>')
    toc.append('<div class="tg"><span class="grp">Références</span><a href="#glossaire">Glossaire</a>'
               '<a href="#journal">Journal</a><a href="#angles">Angles morts</a><a href="#sources">Sources</a></div>')

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
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{html.escape(meta["title"])}</title>
<meta name="description" content="{html.escape(meta["lede"])}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Condensed:wght@500;600;700&family=IBM+Plex+Sans:ital,wght@0,400;0,500;0,600;1,400&display=swap" rel="stylesheet">
<style>{CSS}
ol.log{{list-style:none;padding:0;max-width:76ch}}
ol.log>li{{margin-bottom:14px}}
.watch{{font-size:.85rem;color:var(--ink2);margin-top:18px;max-width:76ch}}
.sources{{list-style:none}}
.sources .num{{display:inline-block;min-width:2.2em;font-variant-numeric:tabular-nums}}
ol.log time{{font-family:"IBM Plex Sans Condensed","Arial Narrow",sans-serif;font-weight:600}}
</style>
</head>
<body>
<button class="themebtn" id="themebtn" type="button">Thème</button>
<div class="wrap">
<header class="top">
<h1>{html.escape(meta["title"])}</h1>
<p class="lede">{html.escape(meta["lede"])}</p>
<p class="meta">Mis à jour le {fr_date(meta["updated"])}. {html.escape(meta["note"])}</p>
<nav class="toc" aria-label="Sommaire">{"".join(toc)}</nav>
</header>
<section id="bref"><h2>En bref</h2><ol class="brief">{brief}</ol>
<h4>Lire selon votre profil</h4>
<div class="profiles">{profiles}</div>
<p class="filterstate" id="filterstate" aria-live="polite"></p>
</section>
{render_matrix(d)}
{parts_html}
<section id="glossaire"><h2>Glossaire</h2><dl class="gloss">{gloss}</dl></section>
<section id="journal"><h2>Journal des mises à jour</h2><ol class="log">{log}</ol></section>
<section id="angles"><h2>Ce que ce dossier ne voit pas</h2><ul>{blind}</ul></section>
<section id="sources"><h2>Sources</h2><ul class="sources">{srcs}</ul></section>
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
  var names={{public:'Grand public',entreprises:'Entreprises',institutions:'Institutions'}};
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
      state.innerHTML='Lecture « '+names[aud]+' » : '+hidden+' section(s) masquée(s). <button type="button" id="showall">Tout afficher</button>';
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


def main():
    d = json.loads(CONTENT.read_text(encoding="utf-8"))
    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "index.html").write_text(render(d), encoding="utf-8")
    (OUT_DIR / ".nojekyll").write_text("", encoding="utf-8")
    print(f"site/index.html écrit ({len(d['sources'])} sources, {len(d['sections'])} sections)")


if __name__ == "__main__":
    main()
