"""YouTube attention per assistant (YouTube Data API v3, key in YOUTUBE_API_KEY, no language model).

Two measures:
- official channels: subscribers, uploads over 30 days and their views (quota: ~3 units per vendor);
- public attention: views of the most viewed videos published in the last 7 days whose title
  mentions the assistant, all creators (search.list: 100 units per vendor).
Weekly total: about 650 units out of the 10,000 daily quota.
"""
import datetime as dt
import json
import os
import re
import urllib.parse
import urllib.request

API = "https://www.googleapis.com/youtube/v3/"
WATCH = "https://www.youtube.com/watch?v={}"

VENDORS = {
    "claude": {"label": "Claude", "handles": ["@anthropic-ai", "@Anthropic", "@claude"],
               "query": "Claude AI", "include": r"\bclaude\b", "exclude": r"debussy|monet|van damme|makelele|shannon"},
    "gpt": {"label": "ChatGPT", "handles": ["@OpenAI"], "query": "ChatGPT",
            "include": r"chatgpt|openai|gpt-?\d", "exclude": r"^$"},
    "gemini": {"label": "Gemini", "handles": ["@googlegemini", "@Gemini", "@GoogleDeepMind"], "query": "Gemini AI",
               "include": r"\bgemini\b", "exclude": r"horoscope|zodiac|astrolog|tarot|crypto|exchange|twins|signo"},
    "grok": {"label": "Grok", "handles": ["@xai", "@xAI_official", "@grok"], "query": "Grok AI",
             "include": r"\bgrok\b", "exclude": r"^$"},
    "meta": {"label": "Meta (Muse)", "handles": ["@aiatmeta"], "query": "Meta AI",
             "include": r"meta ai|muse spark|llama", "exclude": r"^$"},
    "mistral": {"label": "Mistral", "handles": ["@MistralAI", "@mistral-ai", "@mistralai"], "query": "Mistral AI",
                "include": r"\bmistral\b|le chat|vibe", "exclude": r"^$"},
}


def call(endpoint, key, **params):
    params["key"] = key
    url = API + endpoint + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(urllib.request.Request(url, headers={"Accept": "application/json"}), timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def fr(x):
    return f"{int(x):,}".replace(",", " ")


def short(n):
    n = float(n)
    if n >= 1e6:
        return f"{n / 1e6:.1f} M".replace(".", ",")
    if n >= 1e3:
        return f"{n / 1e3:.0f} k"
    return str(int(n))


def video_stats(key, ids):
    out = {}
    for i in range(0, len(ids), 50):
        data = call("videos", key, part="statistics,snippet", id=",".join(ids[i:i + 50]), maxResults=50)
        for v in data.get("items", []):
            out[v["id"]] = {"title": v["snippet"]["title"], "channel": v["snippet"]["channelTitle"],
                            "published": v["snippet"]["publishedAt"],
                            "views": int(v.get("statistics", {}).get("viewCount", 0))}
    return out


def official(key, cfg, since30):
    for h in cfg["handles"]:
        data = call("channels", key, part="snippet,statistics,contentDetails", forHandle=h)
        items = data.get("items") or []
        if not items:
            continue
        ch = items[0]
        uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]
        pl = call("playlistItems", key, part="contentDetails", playlistId=uploads, maxResults=50)
        ids = [it["contentDetails"]["videoId"] for it in pl.get("items", [])
               if it["contentDetails"].get("videoPublishedAt", "") >= since30]
        stats = video_stats(key, ids) if ids else {}
        return {"handle": h, "title": ch["snippet"]["title"],
                "subs": int(ch["statistics"].get("subscriberCount", 0)),
                "n30": len(stats), "views30": sum(v["views"] for v in stats.values())}
    return None


def attention(key, cfg, since7):
    data = call("search", key, part="snippet", q=cfg["query"], type="video", order="viewCount",
                publishedAfter=since7, maxResults=50)
    inc, exc = re.compile(cfg["include"], re.I), re.compile(cfg["exclude"], re.I)
    ids = [it["id"]["videoId"] for it in data.get("items", [])
           if inc.search(it["snippet"]["title"]) and not exc.search(it["snippet"]["title"])]
    stats = video_stats(key, ids) if ids else {}
    top = sorted(stats.items(), key=lambda kv: -kv[1]["views"])[:25]
    return {"views": sum(v["views"] for _, v in top), "n": len(top), "best": top[0] if top else None}


def update_youtube(blocks, state, notes):
    key = os.environ.get("YOUTUBE_API_KEY")
    if not key:
        notes.append("YouTube : clé absente, section non mise à jour.")
        return
    now = dt.datetime.now(dt.timezone.utc)
    since30 = (now - dt.timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    since7 = (now - dt.timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    res = {}
    for vid, cfg in VENDORS.items():
        r = {"off": None, "att": None}
        try:
            r["off"] = official(key, cfg, since30)
            if not r["off"]:
                notes.append(f"YouTube : aucune chaîne officielle trouvée pour {cfg['label']} ({', '.join(cfg['handles'])}).")
        except Exception as e:
            notes.append(f"YouTube, chaîne {cfg['label']} : {e}")
        try:
            r["att"] = attention(key, cfg, since7)
        except Exception as e:
            notes.append(f"YouTube, recherche {cfg['label']} : {e}")
        res[vid] = r
    found = [f"{VENDORS[v]['label']} = {r['off']['handle']}" for v, r in res.items() if r["off"]]
    if found:
        notes.append("YouTube, chaînes officielles retenues : " + " ; ".join(found) + ".")

    snap = state.setdefault("youtube_weekly", {})
    snap[now.date().isoformat()] = {v: {"views7": (r["att"] or {}).get("views"),
                                        "subs": (r["off"] or {}).get("subs"),
                                        "n30": (r["off"] or {}).get("n30")} for v, r in res.items()}
    for k in sorted(snap)[:-52]:
        del snap[k]

    def walk(bs):
        for x in bs:
            yield x
            if x.get("type") == "details":
                yield from walk(x.get("blocks", []))

    ranked = sorted(res.items(), key=lambda kv: -((kv[1]["att"] or {}).get("views") or 0))
    for b in walk(blocks):
        if b.get("auto") == "yt_chart":
            bars = [{"label": VENDORS[v]["label"],
                     "sublabel": f"{r['att']['n']} vidéos retenues",
                     "value": round(r["att"]["views"] / 1e6, 2), "display": short(r["att"]["views"]), "vendor": v}
                    for v, r in ranked if r["att"]]
            b["bars"] = bars
            top = max([x["value"] for x in bars] + [0.1])
            step = next(s for s in (0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500) if s * 5 >= top)
            b["max"] = step * 5
            b["ticks"] = [round(i * step, 1) for i in range(6)]
            b["caption"] = (f"Vues cumulées, au {now.day}/{now.month}/{now.year}, des vidéos publiées dans les 7 derniers jours dont le titre "
                            "mentionne l'assistant, tous créateurs confondus (jusqu'à 25 vidéos parmi les plus vues), en millions [[s95]]. "
                            "Une vidéo critique compte autant qu'une vidéo élogieuse ; la recherche YouTube ne garantit pas l'exhaustivité.")
        if b.get("auto") == "yt_table":
            rows = []
            for v, r in ranked:
                o, a = r["off"], r["att"]
                chan = (f"[{o['title']}](https://www.youtube.com/{o['handle']})" if o else "Non trouvée")
                best = ""
                if a and a["best"]:
                    vid_id, info = a["best"]
                    t = info["title"].replace("[", "(").replace("]", ")")[:80]
                    best = f"[{t}]({WATCH.format(vid_id)}), {short(info['views'])} vues ({info['channel'][:30]})"
                rows.append([VENDORS[v]["label"], chan,
                             short(o["subs"]) if o else "", str(o["n30"]) if o else "",
                             short(o["views30"]) if o else "", best])
            b["rows"] = rows
