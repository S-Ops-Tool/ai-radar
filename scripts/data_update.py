"""Refresh chart data straight from primary datasets, without any language model.

- Epoch AI, AI data centers (CSV, CC-BY)
- Vectara hallucination leaderboard (README table on GitHub)

Charts are identified by their "auto" key in content/dossier.json.
Findings worth a human look (new models, missing models) go to content/briefs/data-AAAA-MM-JJ.md.
"""
import csv
import datetime as dt
import io
import json
import os
import re
import urllib.request

import aa_update
import hn_update
import yt_update
import status_update
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content" / "dossier.json"
STATE = ROOT / "content" / "data_state.json"
BRIEFS = ROOT / "content" / "briefs"

EPOCH_CSV = "https://epoch.ai/data/data_centers/data_centers.csv"
VECTARA_MD = "https://raw.githubusercontent.com/vectara/hallucination-leaderboard/main/README.md"
MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
          "août", "septembre", "octobre", "novembre", "décembre"]
VENDOR_PREFIX = {
    "claude": "anthropic/", "gpt": "openai/", "gemini": "google/gemini",
    "grok": "xai-org/", "meta": "meta-llama/", "mistral": "mistralai/",
}


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "ai-radar/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8")


def fr_num(x, digits=0):
    s = f"{x:,.{digits}f}".replace(",", " ").replace(".", ",")
    return s


def fr_month_year(d):
    return f"{MONTHS[d.month - 1]} {d.year}"


def clean(field):
    parts = [re.sub(r"\s*#\w+", "", p).strip() for p in (field or "").split(",")]
    return [p for p in parts if p]


def confident(field):
    return [re.sub(r"\s*#\w+", "", p).strip() for p in (field or "").split(",")
            if "#likely" not in p and "#speculative" not in p and p.strip()]


PREFIXES = ("Anthropic-Amazon", "Microsoft", "Meta", "OpenAI", "Google", "Amazon", "AWS",
            "xAI", "SpaceXAI", "CoreWeave", "Oracle", "Anthropic")


def short_name(name):
    for p in PREFIXES:
        if name.startswith(p + " ") and len(name) > len(p) + 3:
            return name[len(p) + 1:][:24]
    return name[:24]


def epoch_vendor(owner, users_conf):
    o = " ".join(owner).lower()
    if "spacexai" in o or "xai" in o:
        return "grok"
    if "meta" in o:
        return "meta"
    if "google" in o:
        return "gemini"
    if "mistral" in o:
        return "mistral"
    u = " ".join(users_conf).lower()
    if "anthropic" in u:
        return "claude"
    if "openai" in u:
        return "gpt"
    return "ms"


def update_epoch(block, notes):
    all_rows = list(csv.DictReader(io.StringIO(fetch(EPOCH_CSV))))
    rows = [r for r in all_rows if float(r.get("Current power (MW)") or 0) > 0]
    rows.sort(key=lambda r: float(r["Current power (MW)"]), reverse=True)
    n = int(block.get("top", 5))
    bars = []
    for r in rows[:n]:
        owner = clean(r.get("Owner"))
        users_conf = confident(r.get("Users"))
        mw = float(r["Current power (MW)"])
        sub = ", ".join(owner) or "propriétaire non publié"
        extra = [u for u in users_conf if u not in owner]
        if extra:
            sub += " ; utilisé par " + ", ".join(extra)
        bars.append({"label": short_name(r["Name"]), "sublabel": sub[:60], "value": round(mw),
                     "display": fr_num(mw), "vendor": epoch_vendor(owner, users_conf)})
    total = sum(float(r["Current power (MW)"]) for r in rows)
    block["bars"] = bars
    block["max"] = max(1000, int((bars[0]["value"] // 250 + 1) * 250))
    step = block["max"] // 4
    block["ticks"] = [0, step, 2 * step, 3 * step, block["max"]]
    block.pop("ticklabels", None)
    today = dt.date.today()
    block["caption"] = (f"Puissance IT en service, estimée par Epoch AI (données CC-BY, relevé de {fr_month_year(today)}). "
                        f"Les {len(rows)} sites en service suivis totalisent {fr_num(total / 1000, 1)} GW ; "
                        f"propriétaire et utilisateurs confirmés selon Epoch [[s5]].")
    mistral = [r["Name"] for r in all_rows
               if "mistral" in (r.get("Owner", "") + r.get("Users", "")).lower()]
    if mistral:
        notes.append(f"Sites liés à Mistral dans la base Epoch : {', '.join(mistral)}.")


def parse_date(x):
    if not x:
        return None
    parts = [int(v) for v in x.split("-")]
    return dt.date(parts[0], parts[1], parts[2] if len(parts) > 2 else 15)


def month_gap(a, b):
    if not a or not b:
        return None
    return max(0, round((b - a).days / 30.44))


def update_vectara(block, state, notes):
    md = fetch(VECTARA_MD)
    m = re.search(r"Last updated on ([A-Za-z]+ \d+, \d{4})", md)
    updated = dt.datetime.strptime(m.group(1), "%B %d, %Y").date() if m else None
    table = {}
    for line in md.splitlines():
        mm = re.match(r"^\|([^|]+)\|\s*([\d.]+)\s*%\|", line)
        if mm:
            table[mm.group(1).strip()] = float(mm.group(2))
    rows = []
    for vendor, cfg in block["vendors"].items():
        dots = [{"model": k, "value": v} for k, v in table.items() if k.startswith(cfg["prefix"])]
        tested = dict(cfg["tested"])
        if tested["id"] in table:
            tested["value"] = table[tested["id"]]
        else:
            notes.append(f"Vectara : {tested['id']} absent du classement ; point mis en avant retiré pour {vendor}.")
            tested["value"] = None
        latest = dict(cfg["latest"])
        latest["evaluated"] = bool(latest.get("id") and latest["id"] in table)
        gap = None if latest["evaluated"] else month_gap(parse_date(tested.get("date")), parse_date(latest.get("date")))
        rows.append({"vendor": vendor, "label": cfg["label"], "dots": dots, "tested": tested, "latest": latest, "gap_months": gap})
    rows.sort(key=lambda r: (r["tested"]["value"] is None, r["tested"]["value"] or 0))
    block["rows"] = rows
    top = max([d["value"] for r in rows for d in r["dots"]] + [20])
    block["max"] = int(top // 5 + 1) * 5
    block["ticks"] = list(range(0, block["max"] + 1, 5))
    when = f"classement du {updated.day} {MONTHS[updated.month - 1]} {updated.year}" if updated else "dernier classement"
    block["caption"] = (f"Vectara HHEM, {when} : part des résumés contenant une information absente du document source [[s55]]. "
                        "Points gris : tous les modèles de l'éditeur présents au classement ; point coloré : modèle phare le plus récent testé, avec sa date de sortie. "
                        "Colonne de droite : dernier modèle phare de l'éditeur et écart avec le modèle testé. "
                        "Ce test mesure la fidélité en résumé ; un modèle plus récent peut y faire moins bien qu'un ancien.")
    seen = set(state.get("vectara_seen", []))
    prefixes = [c["prefix"] for c in block["vendors"].values()]
    relevant = {k for k in table if any(k.startswith(p) for p in prefixes)}
    new = sorted(relevant - seen) if seen else []
    if new:
        notes.append("Nouveaux modèles au classement Vectara (à évaluer comme modèle phare) : "
                     + ", ".join(f"{k} ({fr_num(table[k], 1)} %)" for k in new) + ".")
    for vendor, cfg in block["vendors"].items():
        lid = cfg["latest"].get("id")
        if not lid:
            hits = [k for k in new if k.startswith(cfg["prefix"])]
            if hits:
                notes.append(f"{cfg['label']} : vérifier si {', '.join(hits)} correspond au dernier modèle phare ({cfg['latest']['label']}).")
    state["vectara_seen"] = sorted(relevant)


GH_API = "https://api.github.com/repos/vectara/hallucination-leaderboard/commits"
RAW_AT = "https://raw.githubusercontent.com/vectara/hallucination-leaderboard/{sha}/README.md"
MONTHS_SHORT = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]


def gh_json(url):
    headers = {"User-Agent": "ai-radar/1.0", "Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def vectara_table(md):
    table = {}
    for line in md.splitlines():
        mm = re.match(r"^\|([^|]+)\|\s*([\d.]+)\s*%\|", line)
        if mm:
            table[mm.group(1).strip()] = float(mm.group(2))
    return table


def vectara_signature(md):
    """Evaluator version and dataset generation: points with a different signature are not comparable."""
    ev = re.search(r"HHEM-(\d+\.\d+), Vectara's commercial", md)
    return [ev.group(1) if ev else None, "old-dataset" in md.lower()]


def update_vectara_scatter(blocks, vendors_cfg, state, notes):
    """One point per model: x = month the model entered the leaderboard (from git history), y = current rate."""
    now = dt.date.today()
    since = f"{now.year - 2}-{now.month:02d}-01T00:00:00Z"
    commits = []
    for page in range(1, 6):
        batch = gh_json(f"{GH_API}?path=README.md&per_page=100&page={page}&since={since}")
        commits += batch
        if len(batch) < 100:
            break
    dated = sorted((c["commit"]["committer"]["date"], c["sha"]) for c in commits)
    first = state.setdefault("vectara_first_seen", {})
    parsed = set(state.setdefault("vectara_parsed_shas", []))
    new_models = 0
    for date, sha in dated:
        if sha in parsed:
            continue
        for name in vectara_table(fetch(RAW_AT.format(sha=sha))):
            if name not in first or date[:10] < first[name]:
                if name not in first:
                    new_models += 1
                first[name] = date[:10]
        parsed.add(sha)
    state["vectara_parsed_shas"] = sorted(parsed)
    oldest = dated[0][0][:10] if dated else None
    table = vectara_table(fetch(VECTARA_MD))
    pts = []
    for name, rate in table.items():
        vendor = next((v for v, c in vendors_cfg.items() if name.startswith(c["prefix"])), None)
        seen = first.get(name)
        if not vendor or not seen or (oldest and seen <= oldest):
            continue
        pts.append({"x": seen, "y": rate, "vendor": vendor, "label": name.split("/")[-1][:40]})
    if new_models:
        notes.append(f"Vectara : {new_models} modèles datés d'après l'historique du classement.")

    def walk(bs):
        for x in bs:
            yield x
            if x.get("type") == "details":
                yield from walk(x.get("blocks", []))

    for b in walk(blocks):
        if b.get("auto") != "vectara_scatter":
            continue
        b["points"] = sorted(pts, key=lambda p: p["x"])
        b["series"] = [{"key": v, "label": c["label"], "vendor": v} for v, c in vendors_cfg.items()]
        top = max([p["y"] for p in pts] + [10])
        b["max"] = int(top // 5 + 1) * 5
        b["ticks"] = list(range(0, b["max"] + 1, 5))
        start = f"{int(oldest[:4])}-{oldest[5:7]}" if oldest else ""
        b["caption"] = (f"Chaque point est un modèle : en abscisse, le mois de son entrée au classement Vectara, reconstitué depuis l'historique "
                        f"du classement ; en ordonnée, son taux d'hallucination actuel en résumé de documents [[s55]]. {len(pts)} modèles entrés "
                        "depuis le début de l'historique disponible. Le taux affiché est celui mesuré avec la méthode actuelle ; "
                        "une tendance descendante chez un éditeur signale des générations successives plus fidèles.")


def main():
    data = json.loads(CONTENT.read_text(encoding="utf-8"))
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    notes, errors = [], []
    for sec in data["sections"]:
        cfg = next((b for b in sec["blocks"] if b.get("auto") == "status_table"), None)
        if cfg:
            try:
                status_update.update_status(sec["blocks"], state, notes, cfg)
            except Exception as e:
                errors.append(f"statuts : {e}")
        if any(b.get("auto") == "aa_chart" for b in sec["blocks"]):
            try:
                aa_update.update_aa(sec["blocks"], state, notes)
            except Exception as e:
                errors.append(f"artificial analysis : {e}")
        if any(b.get("auto") == "yt_chart" for b in sec["blocks"]):
            try:
                yt_update.update_youtube(sec["blocks"], state, notes)
            except Exception as e:
                errors.append(f"youtube : {e}")
        if any(b.get("auto") == "hn_chart" for b in sec["blocks"]):
            try:
                hn_update.update_hn(sec["blocks"], state, notes)
            except Exception as e:
                errors.append(f"hacker news : {e}")
            try:
                hn_update.update_hn_history(sec["blocks"], state, notes)
            except Exception as e:
                errors.append(f"hacker news, historique : {e}")
        for block in sec["blocks"]:
            auto = block.get("auto")
            try:
                if auto == "epoch_datacenters":
                    update_epoch(block, notes)
                elif auto == "vectara_hhem":
                    update_vectara(block, state, notes)
                    try:
                        update_vectara_scatter(sec["blocks"], block["vendors"], state, notes)
                    except Exception as e:
                        errors.append(f"vectara, historique : {e}")
            except Exception as e:
                errors.append(f"{auto} : {e}")
    CONTENT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    today = dt.date.today().isoformat()
    lines = [f"# Données chiffrées, {today}", ""]
    lines += [f"- {n}" for n in notes] or ["- Aucune observation particulière."]
    if errors:
        lines += ["", "## Erreurs", ""] + [f"- {e}" for e in errors]
    BRIEFS.mkdir(parents=True, exist_ok=True)
    (BRIEFS / f"data-{today}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
