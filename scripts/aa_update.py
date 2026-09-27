"""Capabilities, price and speed from the Artificial Analysis API (free key, no language model).

Tries the V2 free endpoint first, then the legacy endpoint. Parses both response shapes defensively
and reports the received structure in the data brief so the mapping can be adjusted if the API changes.
"""
import json
import os
import urllib.parse
import urllib.request

ENDPOINTS = ["https://artificialanalysis.ai/api/v2/language/models/free",
             "https://artificialanalysis.ai/api/v2/data/llms/models"]
CREATORS = {
    "anthropic": ("claude", "Anthropic"), "openai": ("gpt", "OpenAI"), "google": ("gemini", "Google"),
    "xai": ("grok", "xAI"), "spacexai": ("grok", "xAI"), "meta": ("meta", "Meta"),
    "mistral": ("mistral", "Mistral"), "deepseek": ("ms", "DeepSeek"), "alibaba": ("ms", "Alibaba (Qwen)"),
    "moonshotai": ("ms", "Moonshot (Kimi)"), "zai": ("ms", "Z.ai (GLM)"),
}
MAIN = ["claude", "gpt", "gemini", "grok", "meta", "mistral"]


def get(url, key, page=None):
    if page:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode({"page": page})
    req = urllib.request.Request(url, headers={"x-api-key": key, "Accept": "application/json",
                                               "User-Agent": "ai-radar/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def items_of(payload):
    for k in ("data", "models", "results", "items"):
        if isinstance(payload.get(k), list):
            return payload[k]
    return []


def fetch_all(key, notes):
    last_err = None
    for ep in ENDPOINTS:
        try:
            first = get(ep, key)
            items = items_of(first)
            page = 2
            while items and page <= 20:
                more = items_of(get(ep, key, page))
                if not more or more[0].get("id") == items[0].get("id"):
                    break
                items += more
                page += 1
            if items:
                sample = items[0]
                notes.append(f"Artificial Analysis : {len(items)} modèles via {ep.split('/api/')[1]} ; "
                             f"niveau {first.get('tier', 'n.d.')} ; champs {', '.join(sorted(sample.keys()))[:300]}.")
                return items, first
        except Exception as e:
            last_err = e
    raise RuntimeError(f"aucune réponse exploitable ({last_err})")


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def extract(m):
    creator = m.get("model_creator") or m.get("creator") or {}
    slug = (creator.get("slug") or creator.get("name") or "").lower().replace(" ", "").replace("-", "")
    ev = m.get("evaluations") or {}
    intel = num(ev.get("artificial_analysis_intelligence_index", m.get("artificial_analysis_intelligence_index")))
    pr = m.get("pricing") or {}
    perf = m.get("performance") or m.get("median_performance") or {}
    speed = num(m.get("median_output_tokens_per_second", perf.get("median_output_tokens_per_second",
                                                                 perf.get("output_tokens_per_second"))))
    return {"name": m.get("name") or m.get("slug") or "?", "creator": slug, "intel": intel,
            "pin": num(pr.get("price_1m_input_tokens")), "pout": num(pr.get("price_1m_output_tokens")), "speed": speed}


def fr(x, d=0):
    return "n.d." if x is None else f"{x:,.{d}f}".replace(",", " ").replace(".", ",")


def update_aa(blocks, state, notes):
    key = os.environ.get("ARTIFICIAL_ANALYSIS_API_KEY")
    if not key:
        notes.append("Artificial Analysis : clé absente, section non mise à jour.")
        return
    items, head = fetch_all(key, notes)
    best = {}
    for m in items:
        e = extract(m)
        if e["intel"] is None:
            continue
        match = next((v for k, v in CREATORS.items() if e["creator"].startswith(k)), None)
        if not match:
            continue
        vid, label = match
        cur = best.get(label)
        if cur is None or e["intel"] > cur["intel"]:
            best[label] = dict(e, vendor=vid, label=label)
    if not best:
        raise RuntimeError("aucun modèle des éditeurs suivis dans la réponse")
    version = head.get("intelligence_index_version")
    state["aa_last"] = {k: {x: v[x] for x in ("name", "intel", "pin", "pout", "speed")} for k, v in best.items()}

    def walk(bs):
        for x in bs:
            yield x
            if x.get("type") == "details":
                yield from walk(x.get("blocks", []))

    ranked = sorted(best.values(), key=lambda e: -e["intel"])
    for b in walk(blocks):
        if b.get("auto") == "aa_chart":
            main = [e for e in ranked if e["vendor"] in MAIN]
            b["bars"] = [{"label": e["label"], "sublabel": e["name"][:40], "value": round(e["intel"], 1),
                          "display": fr(e["intel"], 1), "vendor": e["vendor"]} for e in main]
            top = max([e["intel"] for e in main] + [50])
            b["max"] = int(top // 10 + 1) * 10
            step = b["max"] // 5
            b["ticks"] = [i * step for i in range(6)]
            v = f" (version {version})" if version else ""
            b["caption"] = (f"Artificial Analysis Intelligence Index{v} : score composite sur une série de tests de raisonnement, "
                            "de connaissances, de mathématiques et de code, mesurés de façon indépendante [[s93]]. "
                            "Pour chaque éditeur, le modèle le mieux noté ; un éditeur absent n'a aucun modèle évalué.")
        if b.get("auto") == "aa_table":
            b["rows"] = [[e["label"], e["name"][:48], fr(e["intel"], 1),
                          "n.d." if e["pin"] is None else f"{fr(e['pin'], 2)} $ / {fr(e['pout'], 2)} $",
                          fr(e["speed"])] for e in ranked]
    lead = ranked[0]
    notes.append(f"Artificial Analysis : meilleur indice {lead['name']} ({lead['label']}, {fr(lead['intel'], 1)}).")
