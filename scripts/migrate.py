"""Idempotent content migrations, run by the weekly workflow before the data step.

Each migration adds structure to content/dossier.json without touching data already collected,
and records its name in data["migrations"] so it never runs twice.
"""
import json
from pathlib import Path

CONTENT = Path(__file__).resolve().parent.parent / "content" / "dossier.json"


def section(d, sid):
    return next((s for s in d["sections"] if s["id"] == sid), None)


def has_auto(blocks, key):
    for b in blocks:
        if b.get("auto") == key:
            return True
        if b.get("type") == "details" and has_auto(b.get("blocks", []), key):
            return True
    return False


def m_2026_09_history(d):
    per = section(d, "perception")
    if per and not has_auto(per["blocks"], "hn_trend"):
        i = next((k for k, b in enumerate(per["blocks"]) if b.get("auto") == "hn_chart"), 1)
        per["blocks"].insert(i + 1, {"type": "line_chart", "auto": "hn_trend",
                                     "title": "Articles marquants sur Hacker News, par mois",
                                     "max": 10, "ticks": [0, 2, 4, 6, 8, 10], "series": [], "points": [],
                                     "caption": "Historique reconstitué à la prochaine exécution hebdomadaire."})
    pre = section(d, "precision")
    if pre and not has_auto(pre["blocks"], "vectara_trend"):
        i = next((k for k, b in enumerate(pre["blocks"]) if b.get("auto") == "vectara_hhem"), 1)
        pre["blocks"].insert(i + 1, {"type": "details", "summary": "Pour aller plus loin : évolution sur douze mois",
                                     "blocks": [{"type": "line_chart", "auto": "vectara_trend",
                                                 "title": "Meilleur taux d'hallucination de chaque éditeur, fin de mois, en %",
                                                 "max": 20, "ticks": [0, 5, 10, 15, 20], "series": [], "points": [],
                                                 "caption": "Historique reconstitué à la prochaine exécution hebdomadaire."}]})
    d["changelog"].append({"date": "2026-09-27", "items": [
        "Historique sur douze mois pour Hacker News et le classement Vectara, reconstitué à partir des sources d'origine.",
        "Le dossier est désormais disponible en français, anglais, espagnol, allemand et italien ; les traductions sont produites par Claude et relues avec chaque mise à jour."]})


def replace_text(obj, old, new):
    if isinstance(obj, str):
        return obj.replace(old, new)
    if isinstance(obj, list):
        return [replace_text(x, old, new) for x in obj]
    if isinstance(obj, dict):
        return {k: replace_text(v, old, new) for k, v in obj.items()}
    return obj


def m_2026_09_wording(d):
    fixed = replace_text(d["sections"], "Une réponse sans source se vérifie ;", "Une réponse sans source doit être vérifiée ;")
    d["sections"] = fixed


MIGRATIONS = [("2026-09-history", m_2026_09_history), ("2026-09-wording", m_2026_09_wording)]


def main():
    d = json.loads(CONTENT.read_text(encoding="utf-8"))
    done = set(d.get("migrations", []))
    ran = []
    for name, fn in MIGRATIONS:
        if name not in done:
            fn(d)
            ran.append(name)
    if ran:
        d["migrations"] = sorted(done | set(ran))
        CONTENT.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Migrations appliquées : {', '.join(ran) or 'aucune'}")


if __name__ == "__main__":
    main()
