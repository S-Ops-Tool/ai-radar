"""Hacker News attention per assistant (Algolia HN Search API, no key, no language model).

Counts stories whose TITLE mentions each assistant over the last 30 days, the notable ones
(>= NOTABLE points), comments, and lists the top stories of the last 7 days.
A weekly snapshot is appended to content/data_state.json to build a trend over time.
"""
import datetime as dt
import json
import re
import time
import urllib.parse
import urllib.request

API = "https://hn.algolia.com/api/v1/search_by_date"
ITEM = "https://news.ycombinator.com/item?id={}"
NOTABLE = 50

VENDORS = {
    "claude": {"label": "Claude", "queries": ["Claude", "Anthropic"],
               "include": r"\b(claude|anthropic)\b", "exclude": r"\bshannon\b|\bdebussy\b|\bmonet\b"},
    "gpt": {"label": "ChatGPT", "queries": ["ChatGPT", "OpenAI", "GPT-6"],
            "include": r"\b(chatgpt|openai|gpt-?\d)", "exclude": r"^$"},
    "gemini": {"label": "Gemini", "queries": ["Gemini"],
               "include": r"\bgemini\b", "exclude": r"protocol|capsule|gemtext|exchange|crypto|winklevoss|nasa|apollo"},
    "grok": {"label": "Grok", "queries": ["Grok", "xAI"],
             "include": r"\b(grok|xai)\b", "exclude": r"^$"},
    "meta": {"label": "Meta (Muse, Llama)", "queries": ["Meta AI", "Muse Spark", "Llama"],
             "include": r"\b(meta ai|muse spark|llama ?\d|llama\.cpp|meta superintelligence)\b", "exclude": r"^$"},
    "mistral": {"label": "Mistral", "queries": ["Mistral"],
                "include": r"\bmistral\b", "exclude": r"\bwind\b|\bweather\b"},
}


def fetch(params):
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "ai-radar/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def stories_since(query, since_ts):
    hits, page = [], 0
    while True:
        data = fetch({"query": query, "tags": "story", "restrictSearchableAttributes": "title",
                      "numericFilters": f"created_at_i>{since_ts}", "hitsPerPage": 1000, "page": page})
        hits += data.get("hits", [])
        page += 1
        if page >= data.get("nbPages", 0) or page >= 5:
            break
        time.sleep(0.5)
    return hits


def fr(x):
    return f"{x:,}".replace(",", " ")


def update_hn(blocks, state, notes):
    now = dt.datetime.now(dt.timezone.utc)
    since30 = int((now - dt.timedelta(days=30)).timestamp())
    since7 = int((now - dt.timedelta(days=7)).timestamp())
    results = {}
    for vid, cfg in VENDORS.items():
        inc, exc = re.compile(cfg["include"], re.I), re.compile(cfg["exclude"], re.I)
        seen = {}
        for q in cfg["queries"]:
            try:
                for h in stories_since(q, since30):
                    t = h.get("title") or ""
                    if inc.search(t) and not exc.search(t):
                        seen[h["objectID"]] = h
            except Exception as e:
                notes.append(f"Hacker News, requête « {q} » : {e}")
            time.sleep(0.5)
        stories = list(seen.values())
        notable = [s for s in stories if (s.get("points") or 0) >= NOTABLE]
        week = sorted([s for s in stories if (s.get("created_at_i") or 0) >= since7],
                      key=lambda s: -(s.get("points") or 0))
        results[vid] = {"n": len(stories), "notable": len(notable),
                        "comments": sum(s.get("num_comments") or 0 for s in stories),
                        "points": sum(s.get("points") or 0 for s in stories), "top": week[:3]}

    snap = state.setdefault("hn_weekly", {})
    snap[now.date().isoformat()] = {v: {k: r[k] for k in ("n", "notable", "comments", "points")} for v, r in results.items()}
    for k in sorted(snap)[:-52]:
        del snap[k]

    def walk(bs):
        for x in bs:
            yield x
            if x.get("type") == "details":
                yield from walk(x.get("blocks", []))

    for b in walk(blocks):
        if b.get("auto") == "hn_chart":
            b["bars"] = [{"label": VENDORS[v]["label"],
                          "sublabel": f"{fr(r['n'])} articles, {fr(r['comments'])} commentaires",
                          "value": r["notable"], "display": fr(r["notable"]), "vendor": v}
                         for v, r in sorted(results.items(), key=lambda kv: -kv[1]["notable"])]
            top = max([r["notable"] for r in results.values()] + [10])
            b["max"] = int(top // 10 + 1) * 10
            step = max(1, b["max"] // 5)
            b["ticks"] = [i * step for i in range(6)]
            b["caption"] = (f"Articles publiés sur Hacker News au cours des 30 derniers jours dont le titre mentionne l'assistant ou son éditeur, "
                            f"et ayant dépassé {NOTABLE} points ; relevé du {now.day}/{now.month}/{now.year} via l'API Algolia [[s92]]. "
                            "Hacker News reflète l'attention d'un public de développeurs, surtout anglophone ; un article critique compte autant qu'un article élogieux.")
        if b.get("auto") == "hn_top":
            rows = []
            for v, r in sorted(results.items(), key=lambda kv: -kv[1]["notable"]):
                if not r["top"]:
                    rows.append([VENDORS[v]["label"], "Aucun article cette semaine", "", ""])
                    continue
                for i, s in enumerate(r["top"]):
                    title = (s.get("title") or "").replace("[", "(").replace("]", ")")
                    rows.append([VENDORS[v]["label"] if i == 0 else "",
                                 f"[{title}]({ITEM.format(s['objectID'])})",
                                 str(s.get("points") or 0), str(s.get("num_comments") or 0)])
            b["rows"] = rows
    lead = max(results.items(), key=lambda kv: kv[1]["notable"])
    notes.append(f"Hacker News : {VENDORS[lead[0]]['label']} en tête des articles marquants sur 30 jours ({lead[1]['notable']}).")
