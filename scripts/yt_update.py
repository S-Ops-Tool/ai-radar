"""YouTube attention per assistant (YouTube Data API v3, key in YOUTUBE_API_KEY, no language model).

Two measures:
- official channels: subscribers, uploads over 30 days and their views (quota: ~3 units per vendor);
- public attention: views of the most viewed videos published in the last 7 days whose title
  mentions the assistant, all creators (search.list: 2 x 100 units per vendor, medium and long videos).
Weekly total: about 4,300 units out of the 10,000 daily quota.
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
    "claude": {"label": "Claude", "handles": ["@anthropic-ai", "@Anthropic", "@claude"], "names": ["anthropic", "claude"],
               "query": "Claude AI", "include": r"\bclaude\b", "exclude": r"debussy|monet|van damme|makelele|shannon"},
    "gpt": {"label": "ChatGPT", "handles": ["@OpenAI"], "names": ["openai"], "query": "ChatGPT",
            "include": r"chatgpt|openai|gpt-?\d", "exclude": r"^$"},
    "gemini": {"label": "Gemini", "handles": ["@googlegemini", "@GoogleDeepMind"], "names": ["gemini", "google"], "query": "Gemini AI",
               "include": r"\bgemini\b", "exclude": r"horoscope|zodiac|astrolog|tarot|crypto|exchange|twins|signo"},
    "grok": {"label": "Grok", "handles": ["@xai", "@xAI_official", "@grok", "@xAIofficial"], "names": ["xai", "grok"], "query": "Grok AI",
             "include": r"\bgrok\b", "exclude": r"^$"},
    "meta": {"label": "Meta (Muse)", "handles": ["@aiatmeta"], "names": ["meta"], "query": "Meta AI",
             "include": r"meta ai|muse spark|llama", "exclude": r"^$"},
    "mistral": {"label": "Mistral", "handles": ["@MistralAI", "@mistral-ai", "@mistralai", "@MistralAIofficial"], "names": ["mistral"], "query": "Mistral AI",
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


LANGS = ["fr", "en", "es", "de", "it"]


def iso_seconds(d):
    m = re.match(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", d or "")
    if not m:
        return 0
    dd, h, mi, se = (int(x or 0) for x in m.groups())
    return ((dd * 24 + h) * 60 + mi) * 60 + se


def video_stats(key, ids):
    out = {}
    for i in range(0, len(ids), 50):
        data = call("videos", key, part="statistics,snippet,contentDetails", id=",".join(ids[i:i + 50]), maxResults=50)
        for v in data.get("items", []):
            sn = v["snippet"]
            out[v["id"]] = {"title": sn["title"], "channel": sn["channelTitle"],
                            "description": (sn.get("description") or "")[:200],
                            "published": sn["publishedAt"],
                            "lang": (sn.get("defaultAudioLanguage") or sn.get("defaultLanguage") or "").lower(),
                            "seconds": iso_seconds(v.get("contentDetails", {}).get("duration")),
                            "views": int(v.get("statistics", {}).get("viewCount", 0))}
    return out


def best_in_language(key, cfg, since7, lang):
    """Most viewed video of the week, 4 minutes or more, whose declared language matches the page language."""
    data = call("search", key, part="snippet", q=cfg["query"], type="video", order="viewCount",
                publishedAfter=since7, relevanceLanguage=lang, maxResults=50)
    inc, exc = re.compile(cfg["include"], re.I), re.compile(cfg["exclude"] + r"|#shorts?\b", re.I)
    ids = [it["id"]["videoId"] for it in data.get("items", [])
           if inc.search(it["snippet"]["title"]) and not exc.search(it["snippet"]["title"])]
    stats = video_stats(key, ids) if ids else {}
    ok = [(vid, v) for vid, v in stats.items() if v["lang"].startswith(lang) and v["seconds"] >= 240]
    if not ok:
        return None
    vid, v = max(ok, key=lambda kv: kv[1]["views"])
    return {"title": v["title"][:90], "url": WATCH.format(vid), "views": v["views"], "channel": v["channel"][:30]}


MIN_SUBS = 1000


def official(key, cfg, since30, notes):
    for h in cfg["handles"]:
        try:
            data = call("channels", key, part="snippet,statistics,contentDetails", forHandle=h)
        except Exception:
            continue
        items = data.get("items") or []
        if not items:
            continue
        ch = items[0]
        title = ch["snippet"]["title"]
        subs = int(ch["statistics"].get("subscriberCount", 0))
        if not any(n in title.lower() for n in cfg["names"]) or subs < MIN_SUBS:
            notes.append(f"YouTube : {h} écarté pour {cfg['label']} (chaîne « {title[:40]} », {subs} abonnés).")
            continue
        uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]
        pl = call("playlistItems", key, part="contentDetails", playlistId=uploads, maxResults=50)
        ids = [it["contentDetails"]["videoId"] for it in pl.get("items", [])
               if it["contentDetails"].get("videoPublishedAt", "") >= since30]
        stats = video_stats(key, ids) if ids else {}
        return {"handle": h, "title": title, "subs": subs,
                "n30": len(stats), "views30": sum(v["views"] for v in stats.values())}
    return None


def attention(key, cfg, since7):
    """Videos of 4 minutes or more (medium and long), to leave out viral shorts and edits."""
    inc, exc = re.compile(cfg["include"], re.I), re.compile(cfg["exclude"] + r"|#shorts?\b", re.I)
    ids = set()
    for duration in ("medium", "long"):
        data = call("search", key, part="snippet", q=cfg["query"], type="video", order="viewCount",
                    publishedAfter=since7, videoDuration=duration, maxResults=50)
        ids |= {it["id"]["videoId"] for it in data.get("items", [])
                if inc.search(it["snippet"]["title"]) and not exc.search(it["snippet"]["title"])}
    stats = video_stats(key, sorted(ids)) if ids else {}
    top = sorted(stats.items(), key=lambda kv: -kv[1]["views"])[:25]
    return {"views": sum(v["views"] for _, v in top), "n": len(top), "best": top[0] if top else None, "top": top}


CATEGORIES = [
    ("news", "Lancement et actualité", "annonces de modèles ou de fonctions, actualité des éditeurs"),
    ("test", "Test et comparatif", "essais, évaluations, comparaisons entre assistants"),
    ("tutorial", "Tutoriel et usage quotidien", "prise en main, astuces, usages personnels ou scolaires"),
    ("code", "Code et développement", "programmation, agents de code, API, outils pour développeurs"),
    ("business", "Travail, emploi et business", "productivité, entreprise, marché, emploi, finance"),
    ("ethics", "Éthique et responsabilité", "biais, vie privée, désinformation, droits, impact social, controverses éthiques"),
    ("risk", "Risques et sécurité", "incidents, agents incontrôlés, cybersécurité, sûreté des modèles, risques catastrophiques, appels à ralentir"),
    ("culture", "Divertissement et culture", "humour, fiction, art, musique, créations, divertissement"),
]
CLASSIFY_SYSTEM = ("Tu classes des vidéos YouTube sur l'intelligence artificielle d'après leur titre, leur chaîne et le début de leur description, "
                   "dans toutes les langues. Catégories possibles (identifiant : définition) :\n"
                   + "\n".join(f"- {c[0]} : {c[2]}" for c in CATEGORIES)
                   + "\nChoisis la catégorie dominante. Une vidéo qui traite surtout de biais, de vie privée, de droits ou d'impact social "
                   "va dans ethics ; une vidéo qui traite surtout d'incidents, de sûreté, de cybersécurité ou de risques graves va dans risk. Réponds uniquement par un objet JSON {identifiant_video: identifiant_categorie}, sans texte autour.")


def classify(videos, notes):
    """Topic of each video via Claude (closed list); videos left unclassified are reported and excluded."""
    import anthropic
    if not os.environ.get("ANTHROPIC_API_KEY") or not videos:
        return {}
    client = anthropic.Anthropic()
    model = os.environ.get("CLASSIFY_MODEL", "claude-haiku-4-5-20251001")
    valid = {c[0] for c in CATEGORIES}
    out, items = {}, list(videos.items())
    for i in range(0, len(items), 60):
        payload = {vid: f"{v['title']} | {v['channel']} | {v.get('description', '')[:150]}" for vid, v in items[i:i + 60]}
        try:
            resp = client.messages.create(model=model, max_tokens=4000, system=CLASSIFY_SYSTEM,
                                          messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}])
            text = "".join(getattr(b, "text", "") for b in resp.content)
            data = json.loads(text[text.find("{"): text.rfind("}") + 1])
            out.update({k: c for k, c in data.items() if k in payload and c in valid})
        except Exception as e:
            notes.append(f"YouTube, classement thématique : {e}")
    missing = len(videos) - len(out)
    if missing:
        notes.append(f"YouTube : {missing} vidéos non classées, écartées de la répartition par thème.")
    return out


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
            r["off"] = official(key, cfg, since30, notes)
            if not r["off"]:
                notes.append(f"YouTube : aucune chaîne officielle trouvée pour {cfg['label']} ({', '.join(cfg['handles'])}).")
        except Exception as e:
            notes.append(f"YouTube, chaîne {cfg['label']} : {e}")
        try:
            r["att"] = attention(key, cfg, since7)
        except Exception as e:
            notes.append(f"YouTube, recherche {cfg['label']} : {e}")
        r["by_lang"] = {}
        for lang in LANGS:
            try:
                r["by_lang"][lang] = best_in_language(key, cfg, since7, lang)
            except Exception as e:
                notes.append(f"YouTube, recherche {cfg['label']} en {lang} : {e}")
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
    pool = {vid: info for _, r in res.items() for vid, info in ((r["att"] or {}).get("top") or [])}
    cats = classify(pool, notes)
    if cats:
        import random
        sample = random.sample(sorted(cats), min(8, len(cats)))
        notes.append("YouTube, échantillon de classement à vérifier : "
                     + " ; ".join(f"« {pool[v]['title'][:60]} » → {cats[v]}" for v in sample) + ".")
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
                            "mentionne l'assistant, d'une durée de 4 minutes ou plus, tous créateurs et toutes langues confondus (jusqu'à 25 vidéos parmi les plus vues), en millions [[s95]]. "
                            "Les formats courts (Shorts, montages viraux) sont exclus : ils citent souvent un assistant sans en parler. "
                            "Une vidéo critique compte autant qu'une vidéo élogieuse ; la recherche YouTube ne garantit pas l'exhaustivité.")
        if b.get("auto") == "yt_topics":
            b["categories"] = [{"id": c[0], "label": c[1]} for c in CATEGORIES]
            rows = []
            for v, r in ranked:
                top = (r["att"] or {}).get("top") or []
                tot = {}
                for vid, info in top:
                    c = cats.get(vid)
                    if c:
                        tot[c] = tot.get(c, 0) + info["views"]
                s_ = sum(tot.values())
                if s_:
                    rows.append({"vendor": v, "label": VENDORS[v]["label"],
                                 "shares": {c: round(x / s_ * 100, 1) for c, x in tot.items()}})
            b["rows"] = rows
            b["caption"] = (f"Répartition des vues des vidéos retenues cette semaine (jusqu'à 25 par assistant, 4 minutes ou plus), par thème ; "
                            f"relevé du {now.day}/{now.month}/{now.year} [[s95]]. Thème attribué par Claude d'après le titre, la chaîne et le début "
                            "de la description, dans une liste fermée de huit catégories ; un titre ne reflète pas toujours le contenu.")
        if b.get("auto") == "yt_scatter":
            b["categories"] = [{"id": c[0], "label": c[1]} for c in CATEGORIES]
            pts = []
            for v, r in ranked:
                for vid, info in (r["att"] or {}).get("top") or []:
                    if vid in cats:
                        pts.append({"x": info["published"][:10], "views": info["views"], "cat": cats[vid], "vendor": v,
                                    "vtitle": info["title"][:90], "url": WATCH.format(vid), "vchannel": info["channel"][:30]})
            b["points"] = pts
            b["caption"] = ("Chaque point est une vidéo de la semaine : date de publication en abscisse, vues en ordonnée (échelle logarithmique), "
                            "couleur selon le thème. Un clic ouvre la vidéo. Une vidéo qui cite plusieurs assistants apparaît une fois par assistant.")
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
            b["row_vendors"] = [v for v, _ in ranked]
            b["by_lang"] = {v: r.get("by_lang", {}) for v, r in ranked}
