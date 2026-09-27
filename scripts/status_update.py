"""Incidents declared on the vendors' public status pages (no language model).

Statuspage-compatible pages expose /api/v2/incidents.json (last ~50 incidents).
Google publishes a Google Cloud feed (incidents.json) filtered on Gemini / Vertex AI products.
Incidents are accumulated in content/data_state.json so the history grows beyond the API window.
"""
import datetime as dt
import json
import email.utils
import re
import urllib.request
import xml.etree.ElementTree as ET

WINDOW_DAYS = 90
IMPACT_RANK = {"none": 0, "minor": 1, "major": 2, "critical": 3}
GCP_SEVERITY = {"low": "minor", "medium": "major", "high": "critical"}


UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36 ai-radar/1.0 (+https://s-ops-tool.github.io/ai-radar/)")


def fetch_raw(url, accept="application/json"):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8")


def fetch_json(url):
    return json.loads(fetch_raw(url))


def rfc(ts):
    try:
        return email.utils.parsedate_to_datetime(ts)
    except (TypeError, ValueError):
        return None


def xai_incidents(url):
    """xAI RSS: one item per component; merge items sharing the same title and start hour."""
    root = ET.fromstring(fetch_raw(url, "application/rss+xml"))
    groups = {}
    for item in root.iter("item"):
        title = item.findtext("title") or ""
        name = re.sub(r"^\[[^\]]*\]\s*", "", title).strip()
        if re.search(r"\btest\b", name, re.I) or "test+incident" in name.lower():
            continue
        start = rfc(item.findtext("pubDate"))
        if not start:
            continue
        desc = item.findtext("description") or ""
        m = re.search(r"Resolved:\s*([^<]+)</p>", desc)
        end = rfc(m.group(1).strip()) if m else None
        key = (name.lower(), start.strftime("%Y-%m-%dT%H"))
        severe = bool(re.search(r"unavailable|outage|down\b", name, re.I))
        g = groups.setdefault(key, {"name": name[:140], "impact": "major" if severe else "minor",
                                    "start": start, "end": end, "guid": item.findtext("guid") or name})
        if end and (g["end"] is None or end > g["end"]):
            g["end"] = end
    return {g["guid"]: {"name": g["name"], "impact": g["impact"], "start": g["start"].isoformat(),
                        "end": g["end"].isoformat() if g["end"] else None} for g in groups.values()}


def iso(ts):
    if not ts:
        return None
    ts = ts.replace("Z", "+00:00")
    try:
        return dt.datetime.fromisoformat(ts)
    except ValueError:
        return None


def statuspage_incidents(base):
    data = fetch_json(base.rstrip("/") + "/api/v2/incidents.json")
    out = {}
    for inc in data.get("incidents", []):
        start = iso(inc.get("started_at") or inc.get("created_at"))
        if not start:
            continue
        end = iso(inc.get("resolved_at")) or iso(inc.get("monitoring_at"))
        out[inc["id"]] = {"name": (inc.get("name") or "")[:140], "impact": inc.get("impact") or "none",
                          "start": start.isoformat(), "end": end.isoformat() if end else None}
    return out


def gcp_incidents(url, keywords):
    data = fetch_json(url)
    out = {}
    for inc in data:
        products = " ".join(p.get("title", "") for p in inc.get("affected_products", [])) + " " + inc.get("service_name", "")
        if not any(k.lower() in products.lower() for k in keywords):
            continue
        start = iso(inc.get("begin"))
        if not start:
            continue
        end = iso(inc.get("end"))
        out[inc["id"]] = {"name": (inc.get("external_desc") or "")[:140].strip(),
                          "impact": GCP_SEVERITY.get(inc.get("severity", "low"), "minor"),
                          "start": start.isoformat(), "end": end.isoformat() if end else None}
    return out


def fr(x, d=0):
    return f"{x:,.{d}f}".replace(",", " ").replace(".", ",")


def update_status(sec_blocks, state, notes, cfg):
    now = dt.datetime.now(dt.timezone.utc)
    since = now - dt.timedelta(days=WINDOW_DAYS)
    store = state.setdefault("status_incidents", {})
    results = []
    for v in cfg["vendors"]:
        vid, kind = v["id"], v["kind"]
        hist = store.setdefault(vid, {})
        ok = True
        try:
            if kind == "statuspage":
                new = statuspage_incidents(v["url"])
            elif kind == "xai_rss":
                new = xai_incidents(v["url"])
            elif kind == "gcp":
                new = gcp_incidents(v["url"], v.get("keywords", ["Gemini"]))
            else:
                new = {}
                ok = None
            hist.update(new)
        except Exception as e:
            ok = False
            notes.append(f"Page de statut {v['label']} : lecture impossible ({e}).")
        recent = []
        for inc in hist.values():
            s = iso(inc["start"])
            if s and s >= since:
                recent.append(inc)
        hours = 0.0
        for inc in recent:
            s, e = iso(inc["start"]), iso(inc["end"]) or now
            hours += max(0.0, (e - s).total_seconds() / 3600)
        severe = sum(1 for i in recent if IMPACT_RANK.get(i["impact"], 0) >= 2)
        oldest = min((iso(i["start"]) for i in hist.values() if iso(i["start"])), default=None)
        if v.get("since_first_run") and state.get("status_first_run", {}).get(vid):
            first = iso(state["status_first_run"][vid])
            oldest = min(oldest, first) if oldest else first
        covered = oldest is not None and oldest <= since
        days = WINDOW_DAYS if covered else (max(1.0, (now - oldest).total_seconds() / 86400) if oldest else None)
        rate = (len(recent) / days * 30) if days else None
        results.append({"v": v, "ok": ok, "n": len(recent), "severe": severe, "hours": hours, "covered": covered,
                        "oldest": oldest, "days": days, "rate": rate})
        for k in [k for k, inc in hist.items() if iso(inc["start"]) and iso(inc["start"]) < now - dt.timedelta(days=400)]:
            del hist[k]

    rows_chart = [r for r in results if r["ok"] and r["rate"] is not None]
    for b in sec_blocks:
        if b.get("auto") == "status_chart":
            b["bars"] = [{"label": r["v"]["label"],
                          "sublabel": f"{r['n']} incident{'s' if r['n'] > 1 else ''} sur {round(r['days'])} jours"
                                      + ("" if r["covered"] else ", historique partiel"),
                          "value": round(r["rate"], 1), "display": fr(r["rate"], 1), "vendor": r["v"]["id"]}
                         for r in sorted(rows_chart, key=lambda r: -r["rate"])]
            top = max([r["rate"] for r in rows_chart] + [10])
            b["max"] = int(top // 10 + 1) * 10
            step = b["max"] // 5
            b["ticks"] = [i * step for i in range(6)]
            b["caption"] = (f"Nombre moyen d'incidents déclarés par mois sur les pages de statut officielles, calculé sur les {WINDOW_DAYS} derniers jours "
                            f"ou sur la période disponible quand l'historique publié est plus court ; relevé du {now.day}/{now.month}/{now.year}. "
                            "Chaque éditeur choisit ce qu'il déclare et avec quelle granularité : "
                            "un nombre élevé peut refléter une transparence plus grande autant qu'une fiabilité moindre. "
                            "Google : incidents Google Cloud liés à Gemini et Vertex AI, sans l'application grand public.")
        if b.get("auto") == "status_table":
            b["rows"] = []
            for r in results:
                label = r["v"]["label"]
                if r["ok"] is None:
                    b["rows"].append([label, "Pas de page de statut publique", "", "", "", ""])
                    continue
                if r["ok"] is False:
                    b["rows"].append([label, "Lecture impossible cette semaine", "", "", "", r["v"]["src_ref"]])
                    continue
                cov = "complet sur 90 jours" if r["covered"] else (
                    f"partiel, depuis le {r['oldest'].day}/{r['oldest'].month}/{r['oldest'].year}" if r["oldest"] else "aucun incident publié")
                b["rows"].append([label, str(r["n"]), fr(r["rate"], 1) if r["rate"] is not None else "", str(r["severe"]),
                                  f"{fr(r['hours'])} h", f"{cov} {r['v']['src_ref']}"])
    for r in results:
        if r["ok"] and not r["covered"] and r["oldest"]:
            notes.append(f"Statut {r['v']['label']} : historique disponible depuis le {r['oldest'].date()} seulement ; il s'allongera semaine après semaine.")
