"""Weekly refresh of content/dossier.json using the Claude API with web search.

Safety rails:
- one API call per section, so a failure only affects that section;
- the returned JSON must keep the section id and use known block types;
- every new source URL must come from the web searches of that call;
- every [[ref]] must point to an existing or newly added source;
- a section that fails validation keeps its previous version.
"""
import copy
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content" / "dossier.json"
BRIEFS = ROOT / "content" / "briefs"

MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")
WEB_TOOL = os.environ.get("WEB_SEARCH_TOOL", "web_search_20250305")
MAX_SEARCHES = int(os.environ.get("MAX_SEARCHES_PER_SECTION", "6"))
ONLY = [s for s in os.environ.get("ONLY_SECTIONS", "").split(",") if s]

BLOCK_TYPES = {"para", "subhead", "reading", "list", "table", "timeline", "bar_chart", "static", "why", "audiences", "details"}
REF = re.compile(r"\[\[([sn]\d+[a-z]?)\]\]")

SYSTEM = """Tu es analyste en veille technologique. Tu maintiens un dossier comparatif public, en français, sur six assistants IA : Claude (Anthropic), ChatGPT (OpenAI), Gemini (Google), Grok (xAI), Muse (Meta) et Mistral Vibe (Mistral AI).

Registre d'écriture :
- observationnel : le fait d'abord, puis sa lecture éventuelle, clairement séparés ; aucune recommandation à l'impératif ;
- phrases simples et directes ; n'utilise jamais la construction « c'est… ce n'est pas… », ni les oppositions du type « X, pas Y » ;
- le dossier s'adresse à trois publics : grand public, entreprises, institutions. Le bloc audiences donne une phrase par public ; les blocs details regroupent les approfondissements pour spécialistes ;
- pas de superlatifs publicitaires ; les chiffres gardent leurs réserves (source unique, éditeur intéressé, méthode).

Règles de mise à jour :
- cherche des informations publiées depuis la date de dernière mise à jour indiquée ;
- ne modifie un passage que si une source nouvelle et datée le justifie ; sinon laisse-le tel quel, au mot près ;
- chaque affirmation nouvelle ou modifiée porte une référence [[id]] ; pour une nouvelle source, utilise un identifiant temporaire [[n1]], [[n2]]… déclaré dans new_sources ;
- privilégie les sources primaires (éditeurs, publications scientifiques, régulateurs, tribunaux, presse de référence) ; signale les sources commerciales comme telles ;
- tu es toi-même Claude : applique un niveau de preuve au moins aussi exigeant aux informations favorables à Anthropic ;
- conserve la structure JSON existante et les types de blocs autorisés : why, para, subhead, reading, list, table, timeline, bar_chart, static, audiences, details (ce dernier contient une liste blocks) ;
- l'essentiel reste visible ; un détail technique ou une donnée secondaire va dans un bloc details.

Réponds uniquement par un objet JSON, sans texte autour ni balises de code, de la forme :
{"section": {...section complète mise à jour...}, "new_sources": {"n1": {"title": "...", "url": "..."}}, "changes": ["phrase courte décrivant chaque changement, avec ses références [[id]]"]}
Si rien de significatif n'a changé, renvoie la section inchangée, new_sources vide et changes vide."""


def extract_json(text):
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("aucun objet JSON dans la réponse")
    return json.loads(text[start:end + 1])


def norm(url):
    return url.split("#")[0].rstrip("/").lower()


def call_claude(client, prompt, use_search=True):
    messages = [{"role": "user", "content": prompt}]
    urls = set()
    tools = [{"type": WEB_TOOL, "name": "web_search", "max_uses": MAX_SEARCHES}] if use_search else []
    for _ in range(6):
        kwargs = dict(model=MODEL, max_tokens=16000, system=SYSTEM, messages=messages)
        if tools:
            kwargs["tools"] = tools
        resp = client.messages.create(**kwargs)
        for block in resp.content:
            if getattr(block, "type", "") == "web_search_tool_result":
                content = getattr(block, "content", None)
                if isinstance(content, list):
                    for r in content:
                        u = getattr(r, "url", None)
                        if u:
                            urls.add(norm(u))
            for cit in getattr(block, "citations", None) or []:
                u = getattr(cit, "url", None)
                if u:
                    urls.add(norm(u))
        if resp.stop_reason == "pause_turn":
            messages = messages + [{"role": "assistant", "content": resp.content}]
            continue
        text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text")
        return text, urls
    raise RuntimeError("trop d'itérations pause_turn")


def walk_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, list):
        for x in obj:
            yield from walk_strings(x)
    elif isinstance(obj, dict):
        for x in obj.values():
            yield from walk_strings(x)


def remap(obj, mapping):
    if isinstance(obj, str):
        return REF.sub(lambda m: f"[[{mapping.get(m.group(1), m.group(1))}]]", obj)
    if isinstance(obj, list):
        return [remap(x, mapping) for x in obj]
    if isinstance(obj, dict):
        return {k: remap(v, mapping) for k, v in obj.items()}
    return obj


def validate_blocks(blocks, depth=0):
    for b in blocks:
        t = b.get("type")
        if t not in BLOCK_TYPES:
            raise ValueError(f"type de bloc inconnu : {t}")
        if t == "static" and b.get("name") != "pipeline":
            raise ValueError("bloc static inconnu")
        if t == "bar_chart":
            float(b["max"])
            for bar in b["bars"]:
                float(bar["value"])
        if t == "audiences" and not all(isinstance(b.get(k), str) for k in ("public", "entreprises", "institutions")):
            raise ValueError("bloc audiences incomplet")
        if t == "details":
            if depth > 0 or not isinstance(b.get("blocks"), list) or not b.get("summary"):
                raise ValueError("bloc details invalide")
            validate_blocks(b["blocks"], depth + 1)


def validate_section(old, new):
    if not isinstance(new, dict) or new.get("id") != old["id"]:
        raise ValueError("identifiant de section modifié")
    if not isinstance(new.get("title"), str) or not isinstance(new.get("blocks"), list) or not new["blocks"]:
        raise ValueError("titre ou blocs manquants")
    validate_blocks(new["blocks"])


def protect(old, new):
    """Keep the watch list and data-driven blocks exactly as they were."""
    new["watch"] = old.get("watch", [])
    if old.get("for"):
        new["for"] = old["for"]
    autos = {b["auto"]: b for b in old["blocks"] if b.get("auto")}
    blocks, placed = [], set()
    for b in new["blocks"]:
        key = b.get("auto")
        if key in autos:
            blocks.append(autos[key])
            placed.add(key)
        elif not key:
            blocks.append(b)
    for i, b in enumerate(old["blocks"]):
        if b.get("auto") and b["auto"] not in placed:
            blocks.insert(min(i, len(blocks)), b)
    new["blocks"] = blocks
    return new


def next_id(sources):
    nums = [int(re.sub(r"\D", "", k)) for k in sources if re.sub(r"\D", "", k)]
    return max(nums or [0]) + 1


def update_section(client, data, idx, today):
    sec = data["sections"][idx]
    catalog = "\n".join(f"{k}: {v['title']}" for k, v in data["sources"].items())
    watch = "\n".join(f"- {w}" for w in sec.get("watch", [])) or "- (aucune)"
    prompt = (
        f"Date du jour : {today}. Dernière mise à jour du dossier : {data['meta']['updated']}.\n\n"
        f"Sources déjà référencées (identifiant : titre) :\n{catalog}\n\n"
        f"Sources primaires à consulter en priorité :\n{watch}\n\n"
        "Les blocs portant une clé auto sont alimentés par un script de données : ne les modifie pas.\n\n"
        f"Section à mettre à jour :\n{json.dumps(sec, ensure_ascii=False, indent=1)}\n\n"
        "Recherche les faits nouveaux, études, chiffres ou décisions publiés depuis la dernière mise à jour "
        "qui modifient ou complètent cette section pour l'un des six assistants, puis renvoie le JSON demandé."
    )
    text, urls = call_claude(client, prompt)
    result = extract_json(text)
    new_sec = result.get("section")
    validate_section(sec, new_sec)
    new_sec = protect(sec, new_sec)
    new_sources = result.get("new_sources") or {}
    mapping, added = {}, {}
    n = next_id(data["sources"])
    for tmp, s in new_sources.items():
        url = (s or {}).get("url", "")
        if not url.startswith("http") or norm(url) not in urls:
            raise ValueError(f"source non issue des recherches : {url}")
        sid = f"s{n}"
        n += 1
        mapping[tmp] = sid
        added[sid] = {"title": s.get("title", url)[:160], "url": url}
    new_sec = remap(new_sec, mapping)
    changes = [c for c in remap(result.get("changes") or [], mapping) if isinstance(c, str)]
    known = set(data["sources"]) | set(added)
    for s in walk_strings(new_sec):
        for ref in REF.findall(s):
            if ref not in known:
                raise ValueError(f"référence inconnue : {ref}")
    return new_sec, added, changes


def update_matrix(client, data, all_changes, today):
    prompt = (
        f"Date du jour : {today}. Voici la matrice de lecture du dossier et la liste des changements de la semaine.\n\n"
        f"Matrice :\n{json.dumps(data['matrix'], ensure_ascii=False, indent=1)}\n\n"
        f"Constats clés en tête de page :\n{json.dumps(data.get('keypoints', []), ensure_ascii=False, indent=1)}\n\n"
        f"Changements :\n" + "\n".join(f"- {c}" for c in all_changes) + "\n\n"
        "Ajuste uniquement les cellules que ces changements justifient (band de 1 à 5, ou null si aucune donnée publique ; "
        "text de moins de 60 caractères). Ne touche pas aux cellules textonly sauf si un changement l'exige. "
        "Ajuste de même les constats clés (3 à 6 phrases, chacune avec ses références [[id]] existantes) uniquement si les changements le justifient. "
        'Réponds uniquement par {"matrix": [...], "keypoints": [...], "changes": ["..."]}.'
    )
    text, _ = call_claude(client, prompt, use_search=False)
    result = extract_json(text)
    matrix = result["matrix"]
    if [r["label"] for r in matrix] != [r["label"] for r in data["matrix"]]:
        raise ValueError("lignes de la matrice modifiées")
    for r in matrix:
        for v in data["vendors"]:
            c = r["cells"][v["id"]]
            if c.get("band") is not None and int(c["band"]) not in range(1, 6):
                raise ValueError("bande hors plage")
    keypoints = result.get("keypoints") or data.get("keypoints", [])
    if not (3 <= len(keypoints) <= 6) or not all(isinstance(k, str) for k in keypoints):
        raise ValueError("constats clés invalides")
    for k in keypoints:
        for ref in REF.findall(k):
            if ref not in data["sources"]:
                raise ValueError(f"référence inconnue dans les constats : {ref}")
    return matrix, keypoints, [c for c in result.get("changes") or [] if isinstance(c, str)]


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY manquante")
    client = anthropic.Anthropic()
    data = json.loads(CONTENT.read_text(encoding="utf-8"))
    original = copy.deepcopy(data)
    today = dt.date.today().isoformat()
    all_changes, errors = [], []

    for i, sec in enumerate(data["sections"]):
        if ONLY and sec["id"] not in ONLY:
            continue
        try:
            new_sec, added, changes = update_section(client, data, i, today)
            data["sections"][i] = new_sec
            data["sources"].update(added)
            all_changes += changes
            print(f"[ok] {sec['id']} : {len(changes)} changement(s), {len(added)} source(s)")
        except Exception as e:
            errors.append(f"{sec['id']} : {e}")
            print(f"[rejeté] {sec['id']} : {e}")

    if all_changes:
        try:
            matrix, keypoints, mchanges = update_matrix(client, data, all_changes, today)
            data["matrix"] = matrix
            data["keypoints"] = keypoints
            all_changes += mchanges
        except Exception as e:
            errors.append(f"matrice : {e}")

    BRIEFS.mkdir(parents=True, exist_ok=True)
    lines = [f"# Mise à jour du {today}", ""]
    if all_changes:
        lines += ["## Changements", ""] + [f"- {c}" for c in all_changes] + [""]
        new_ids = sorted(set(data["sources"]) - set(original["sources"]), key=lambda k: int(k[1:]))
        if new_ids:
            lines += ["## Nouvelles sources", ""]
            lines += [f"- {k} : [{data['sources'][k]['title']}]({data['sources'][k]['url']})" for k in new_ids]
            lines.append("")
    else:
        lines += ["Aucun changement significatif détecté.", ""]
    if errors:
        lines += ["## Mises à jour rejetées par la validation", ""] + [f"- {e}" for e in errors] + [""]
    lines = [REF.sub(lambda m: f"[{m.group(1)}]", ln) for ln in lines]
    (BRIEFS / f"{today}.md").write_text("\n".join(lines), encoding="utf-8")

    if all_changes:
        data["meta"]["updated"] = today
        data["changelog"].append({"date": today, "items": all_changes})
    CONTENT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    print(f"{len(all_changes)} changement(s), {len(errors)} rejet(s)")


if __name__ == "__main__":
    main()
