"""Translate the French dossier into en, es, de, it (Claude API), incrementally.

- Every translatable string of content/dossier.json is keyed by the SHA-1 of its French text.
- content/i18n/<lang>.json caches {hash: {"fr": ..., "tr": ...}}; only new or changed strings are sent.
- A translation is accepted only if it keeps the same [[sN]] source markers and the same [text](url) links.
- Strings no longer used are removed from the cache, so it stays the size of the dossier.
"""
import hashlib
import json
import os
import re
import sys
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build  # noqa: E402  (SKIP_KEYS, paths)

ROOT = Path(__file__).resolve().parent.parent
I18N = ROOT / "content" / "i18n"
MODEL = os.environ.get("TRANSLATE_MODEL", "claude-sonnet-5")
TARGETS = {"en": "anglais (international)", "es": "espagnol (Espagne)", "de": "allemand (Suisse et Allemagne, orthographe avec ss)",
           "it": "italien (Suisse italienne et Italie)"}
MARK = re.compile(r"\[\[[a-z]\d+[a-z]?\]\]")
LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
LETTER = re.compile(r"[A-Za-zÀ-ÿ]")

SYSTEM = """Tu es traducteur professionnel spécialisé en technologie, en économie et en politique publique.
Tu traduis depuis le français les textes d'un dossier public comparant des assistants d'intelligence artificielle.

Règles impératives :
- conserve exactement, à la même place logique, chaque marqueur de source de la forme [[s12]] ;
- conserve exactement chaque lien de la forme [texte](url), texte et adresse compris : ce sont des titres d'articles ou de vidéos, laissés dans leur langue d'origine ;
- ne traduis pas les noms de produits, de modèles, d'entreprises, d'organismes ni de tests (Claude Opus 5.5, Vectara HHEM, Artificial Analysis, AI Act, nLPD…) ; traduis les noms de lois ou d'autorités seulement s'ils ont un équivalent officiel établi ;
- adapte la typographie à la langue cible : séparateur décimal, espaces, guillemets, ponctuation ;
- garde le registre : factuel, observationnel, phrases simples et directes, sans ajouter ni retirer d'information ; les libellés courts restent courts ;
- n'utilise pas de formules d'opposition du type « X, pas Y » si le texte source ne les contient pas.

Tu reçois un objet JSON {identifiant: texte}. Réponds uniquement par un objet JSON {identifiant: traduction} avec exactement les mêmes identifiants, sans texte autour ni balises de code."""


def key(s):
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:16]


def collect(obj, out, k=None):
    if isinstance(obj, str):
        if k not in build.SKIP_KEYS and LETTER.search(obj):
            out.add(obj)
    elif isinstance(obj, list):
        if k == "sections" and all(isinstance(x, str) for x in obj):
            return
        for x in obj:
            collect(x, out, k)
    elif isinstance(obj, dict):
        for kk, v in obj.items():
            collect(v, out, kk)


def valid(src, tr):
    if not isinstance(tr, str) or not tr.strip():
        return False
    if sorted(MARK.findall(src)) != sorted(MARK.findall(tr)):
        return False
    return sorted(LINK.findall(src)) == sorted(LINK.findall(tr))


def extract_json(text):
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if m:
        text = m.group(1)
    return json.loads(text[text.find("{"): text.rfind("}") + 1])


def batches(items, max_chars=9000, max_items=60):
    cur, size = [], 0
    for k, s in items:
        if cur and (size + len(s) > max_chars or len(cur) >= max_items):
            yield cur
            cur, size = [], 0
        cur.append((k, s))
        size += len(s)
    if cur:
        yield cur


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY manquante")
    client = anthropic.Anthropic()
    data = json.loads(build.CONTENT.read_text(encoding="utf-8"))
    strings = set()
    collect(data, strings)
    wanted = {key(s): s for s in strings}
    I18N.mkdir(parents=True, exist_ok=True)
    report = []
    for lang, desc in TARGETS.items():
        path = I18N / f"{lang}.json"
        cache = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        cache = {k: v for k, v in cache.items() if k in wanted}
        todo = [(k, s) for k, s in wanted.items() if k not in cache]
        done = failed = 0
        for batch in batches(todo):
            payload = {k: s for k, s in batch}
            try:
                resp = client.messages.create(
                    model=MODEL, max_tokens=16000, system=SYSTEM,
                    messages=[{"role": "user", "content": f"Langue cible : {desc}.\n\n" + json.dumps(payload, ensure_ascii=False)}])
                out = extract_json("".join(getattr(b, "text", "") for b in resp.content))
            except Exception as e:
                print(f"[{lang}] lot rejeté : {e}")
                failed += len(batch)
                continue
            for k, s in batch:
                tr = out.get(k)
                if valid(s, tr):
                    cache[k] = {"fr": s, "tr": tr.strip()}
                    done += 1
                else:
                    failed += 1
        path.write_text(json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        report.append(f"{lang} : {done} textes traduits, {failed} en échec (affichés en français), {len(cache)}/{len(wanted)} couverts")
        print(report[-1])
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("\n## Traductions\n\n" + "\n".join(f"- {r}" for r in report) + "\n")


if __name__ == "__main__":
    main()
