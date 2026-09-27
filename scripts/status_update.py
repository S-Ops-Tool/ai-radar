"""Incidents declared on the vendors' public status pages (no language model).

Statuspage-compatible pages expose /api/v2/incidents.json (last ~50 incidents).
Google publishes a Google Cloud feed (incidents.json) filtered on Gemini / Vertex AI products.
Incidents are accumulated in content/data_state.json so the history grows beyond the API window.
"""
import datetime as dt
import json
import urllib.request

WINDOW_DAYS = 90
IMPACT_RANK = {"none": 0, "minor": 1, "major": 2, "critical": 3}
GCP_SEVERITY = {"low": "minor", "medium": "major", "high": "critical"}


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "ai-radar/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


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
        covered = oldest is not None and oldest <= since
        results.append({"v": v, "ok": ok, "n": len(recent), "severe": severe, "hours": hours, "covered": covered, "oldest": oldest})
        for k in [k for k, inc in hist.items() if iso(inc["start"]) and iso(inc["start"]) < now - dt.timedelta(days=400)]:
            del hist[k]

    rows_chart = [r for r in results if r["ok"] is not False and r["ok"] is not None]
    for b in sec_blocks:
        if b.get("auto") == "status_chart":
            b["bars"] = [{"label": r["v"]["label"], "sublabel": f"dont {r['severe']} majeur{'s' if r['severe'] > 1 else ''} ou critique{'s' if r['severe'] > 1 else ''}",
                          "value": r["n"], "display": str(r["n"]), "vendor": r["v"]["id"]}
                         for r in sorted(rows_chart, key=lambda r: -r["n"])]
            top = max([r["n"] for r in rows_chart] + [10])
            b["max"] = int(top // 10 + 1) * 10
            step = b["max"] // 5
            b["ticks"] = [i * step for i in range(6)]
            b["caption"] = (f"Incidents déclarés sur les pages de statut officielles au cours des {WINDOW_DAYS} derniers jours, relevé du "
                            f"{now.day}/{now.month}/{now.year}. Chaque éditeur choisit ce qu'il déclare et avec quelle granularité : "
                            "un nombre élevé peut refléter une transparence plus grande autant qu'une fiabilité moindre. "
                            "Google : incidents Google Cloud liés à Gemini et Vertex AI, sans l'application grand public.")
        if b.get("auto") == "status_table":
            b["rows"] = []
            for r in results:
                label = r["v"]["label"]
                if r["ok"] is None:
                    b["rows"].append([label, "Pas de page de statut publique", "", "", ""])
                    continue
                if r["ok"] is False:
                    b["rows"].append([label, "Lecture impossible cette semaine", "", "", r["v"]["src_ref"]])
                    continue
                cov = "complet sur 90 jours" if r["covered"] else (
                    f"depuis le {r['oldest'].day}/{r['oldest'].month}/{r['oldest'].year}" if r["oldest"] else "aucun incident publié")
                b["rows"].append([label, str(r["n"]), str(r["severe"]), f"{fr(r['hours'])} h", f"{cov} {r['v']['src_ref']}"])
    for r in results:
        if r["ok"] and not r["covered"] and r["oldest"]:
            notes.append(f"Statut {r['v']['label']} : historique disponible depuis le {r['oldest'].date()} seulement ; il s'allongera semaine après semaine.")
