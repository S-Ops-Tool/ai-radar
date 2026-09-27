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
    return (f'<figure class="chart"><h3>{html.escape(b["title"])}</h3>'
            f'<div class="scroll" style="margin:0">{"".join(parts)}</div>{cap}</figure>')


def render_block(b, sources):
    t = b["type"]
    if t == "para":
        return f"<p>{txt(b['text'], sources)}</p>"
    if t == "subhead":
        return f"<h3>{html.escape(b['text'])}</h3>"
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
    if t == "static":
        svg = STATIC.get(b["name"], "")
        cap = f'<figcaption>{txt(b["caption"], sources)}</figcaption>' if b.get("caption") else ""
        return f'<figure class="chart"><div class="scroll" style="margin:0">{svg}</div>{cap}</figure>'
    return ""


def render(d):
    sources = d["sources"]
    meta = d["meta"]
    toc = ['<a href="#matrice">Matrice</a>']
    toc += [f'<a href="#{s["id"]}">{html.escape(s["title"].split(" :")[0])}</a>' for s in d["sections"]]
    toc += ['<a href="#journal">Journal des mises à jour</a>', '<a href="#angles">Angles morts</a>', '<a href="#sources">Sources</a>']
    sections = "".join(
        f'<section id="{s["id"]}"><h2>{html.escape(s["title"])}</h2>'
        + "".join(render_block(b, sources) for b in s["blocks"])
        + (f'<p class="watch">Sources suivies chaque semaine : {html.escape(", ".join(s["watch"]))}.</p>' if s.get("watch") else "")
        + "</section>"
        for s in d["sections"])
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
.watch{{font-size:.85rem;color:var(--ink2);margin-top:22px;max-width:76ch}}
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
{render_matrix(d)}
{sections}
<section id="journal"><h2>Journal des mises à jour</h2><ol class="log">{log}</ol></section>
<section id="angles"><h2>Ce que ce dossier ne voit pas</h2><ul>{blind}</ul></section>
<section id="sources"><h2>Sources</h2><ul class="sources">{srcs}</ul></section>
</div>
<script>
(function(){{
  var btn=document.getElementById('themebtn'),root=document.documentElement,saved=null;
  try{{saved=localStorage.getItem('theme');}}catch(e){{}}
  if(saved==='light'||saved==='dark'){{root.setAttribute('data-theme',saved);}}
  btn.addEventListener('click',function(){{
    var cur=root.getAttribute('data-theme');
    if(!cur){{cur=window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';}}
    var next=cur==='dark'?'light':'dark';
    root.setAttribute('data-theme',next);
    try{{localStorage.setItem('theme',next);}}catch(e){{}}
  }});
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
