"""Idempotent content migrations, run by the weekly workflow before the data step.

Each migration adds structure to content/dossier.json without touching data already collected,
and records its name in data["migrations"] so it never runs twice.
"""
import json
import sys
from pathlib import Path

CONTENT = Path(__file__).resolve().parent.parent / "content" / "dossier.json"
sys.path.insert(0, str(Path(__file__).resolve().parent))


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


def m_2026_09_scatter_lang(d):
    pre = section(d, "precision")
    if pre:
        for b in pre["blocks"]:
            if b.get("type") == "details" and has_auto(b.get("blocks", []), "vectara_trend"):
                b["summary"] = "Pour aller plus loin : les nouveaux modèles hallucinent-ils moins ?"
                b["blocks"] = [{"type": "scatter_chart", "auto": "vectara_scatter",
                                "title": "Taux d'hallucination selon la date d'entrée au classement, un point par modèle, en %",
                                "max": 20, "ticks": [0, 5, 10, 15, 20], "series": [], "points": [],
                                "caption": "Premier relevé à la prochaine exécution hebdomadaire."}]
    vid = section(d, "video")
    if vid:
        for b in vid["blocks"]:
            if b.get("auto") == "yt_chart":
                b["title"] = "Vues des vidéos de la semaine citant l'assistant, monde entier, en millions"
            if b.get("type") == "details":
                for x in b.get("blocks", []):
                    if x.get("auto") == "yt_table":
                        x["headers"] = ["Assistant", "Chaîne officielle", "Abonnés", "Vidéos (30 jours)", "Vues de ces vidéos",
                                        "Vidéo la plus vue de la semaine, monde entier", "Vidéo la plus vue dans la langue de cette page"]
                    if x.get("type") == "list":
                        x["items"].append("Une vidéo de synthèse qui cite plusieurs assistants compte pour chacun d'eux.")
                        x["items"].append("La dernière colonne retient les vidéos dont la langue déclarée correspond à celle de la page, d'une durée de 4 minutes ou plus.")
    d["changelog"].append({"date": "2026-09-27", "items": [
        "Fiabilité : l'évolution mensuelle du meilleur taux, peu informative, est remplacée par un nuage de points qui situe chaque modèle selon sa date d'entrée au classement Vectara.",
        "YouTube : la vidéo la plus vue de la semaine est aussi indiquée dans la langue de chaque version du site."]})


ETHICS = {
    "id": "ethique", "title": "Éthique : les pratiques des éditeurs face aux principes reconnus",
    "for": ["public", "entreprises", "institutions"],
    "watch": ["UNESCO, Recommandation sur l'éthique de l'IA", "OCDE, Principes sur l'IA",
              "Commission européenne, code de bonnes pratiques de l'AI Act et ses signataires",
              "Rapports de transparence et de menace des éditeurs"],
    "blocks": [
        {"type": "why", "text": "Les référentiels publics d'éthique de l'IA fixent des attentes communes ; les confronter aux pratiques documentées montre où chaque éditeur s'engage et où il se tient en retrait."},
        {"type": "para", "text": "Le tableau confronte les pratiques documentées dans ce dossier à sept principes communs à la Recommandation de l'UNESCO sur l'éthique de l'IA [[s99]], aux Principes de l'OCDE sur l'IA [[s100]] et aux obligations de l'AI Act. Il ne note pas les éditeurs : chaque case résume un fait sourcé, ou signale l'absence d'information publique."},
        {"type": "table", "headers": ["Principe", "Claude", "ChatGPT", "Gemini", "Grok", "Muse (Meta)", "Mistral Vibe"], "rows": [
            ["Transparence sur les données d'entraînement (UNESCO, AI Act)",
             "Signataire du code de bonnes pratiques de l'AI Act, qui prévoit un résumé public des données [[s97]]",
             "Signataire du code [[s97]]", "Signataire du code [[s97]]",
             "Chapitre sécurité seulement : transparence à démontrer par d'autres moyens [[s97]]",
             "Refus de signer le code [[s98]]", "Signataire du code [[s97]]"],
            ["Respect du droit d'auteur (UNESCO, AI Act)",
             "Accord de 1,5 Md$ pour l'usage de livres piratés [[s31]]", "Condamnation en Allemagne pour mémorisation de paroles [[s33]]",
             "Plainte pour retrait de métadonnées de droits d'auteur [[s32]]", "Distillation partielle de modèles GPT admise [[s35]]",
             "Volet téléchargement par torrent toujours ouvert [[s34]]", "Aucun litige majeur trouvé"],
            ["Vie privée et consentement (UNESCO, OCDE)",
             "Choix explicite demandé depuis 2025 [[s77]]", "Entraînement sur les conversations activé par défaut, désactivable [[s76]]",
             "Activé par défaut, y compris en offre payante [[s76]]", "Publications X utilisées par défaut [[s78]]",
             "Pas de désactivation simple ; conversations utilisées pour la publicité [[s80]] [[s41]]", "Non vérifié"],
            ["Sécurité et évaluation des risques (UNESCO, OCDE)",
             "C+ à l'AI Safety Index ; chapitre sécurité du code signé [[s1]] [[s97]]", "C ; chapitre sécurité signé [[s1]] [[s97]]",
             "C ; chapitre sécurité signé [[s1]] [[s97]]", "F ; chapitre sécurité signé [[s1]] [[s97]]",
             "D+ ; code non signé [[s1]] [[s98]]", "F ; signataire du code [[s1]] [[s97]]"],
            ["Équité et non-discrimination (UNESCO, OCDE)",
             "Aucune évaluation indépendante comparable trouvée", "Aucune évaluation indépendante comparable trouvée",
             "Aucune évaluation indépendante comparable trouvée", "Réponses orientées relevées sur les sujets politiques [[s53]]",
             "Aucune évaluation indépendante comparable trouvée", "Aucune évaluation indépendante comparable trouvée"],
            ["Durabilité environnementale (UNESCO, OCDE)",
             "Aucun chiffre publié [[s28]]", "Un chiffre par requête, sans méthode [[s26]]", "Méthode de mesure publiée [[s24]]",
             "Électricité en partie produite au gaz sur site [[s7]]", "Aucun chiffre par requête trouvé", "Analyse de cycle de vie publiée [[s27]]"],
            ["Responsabilité face aux abus (UNESCO, OCDE)",
             "Rapports de menace publiés [[s19]] [[s22]]", "Rapports de menace publiés depuis deux ans [[s101]]",
             "Non vérifié dans les sources consultées", "87 % des fichiers deepfake liés à des attaques au premier semestre 2026, selon Resemble AI [[s38]]",
             "Aucun rapport public trouvé", "Aucun rapport public trouvé"]]},
        {"type": "reading", "text": "Aucun éditeur ne répond à tous les principes. Les engagements les plus visibles portent sur la sécurité et la transparence réglementaire ; l'équité reste le principe le moins documenté, faute d'évaluation indépendante comparable. Signer un code ou publier un rapport engage l'éditeur, sans garantir la pratique : la colonne « droit d'auteur » montre l'écart possible entre engagements et contentieux."},
        {"type": "audiences",
         "public": "Les réglages de confidentialité et la politique d'entraînement sur les conversations sont les leviers éthiques les plus directs pour un utilisateur.",
         "entreprises": "La signature du code de l'AI Act et la transparence sur les données comptent dans l'évaluation des fournisseurs et dans le reporting de durabilité.",
         "institutions": "Les écarts entre éditeurs sur ces principes éclairent les critères d'achat public et le suivi de l'AI Act."},
        {"type": "details", "summary": "Pour aller plus loin : les référentiels utilisés", "blocks": [
            {"type": "list", "items": [
                "La Recommandation de l'UNESCO sur l'éthique de l'intelligence artificielle, adoptée en 2021 par les États membres, pose notamment les principes de sécurité, de vie privée, de transparence, de responsabilité, d'équité et de durabilité [[s99]].",
                "Les Principes de l'OCDE sur l'IA, adoptés en 2019 et actualisés en 2024, couvrent la croissance inclusive et le développement durable, les droits humains, la transparence, la robustesse et la sécurité, et la redevabilité [[s100]].",
                "Le code de bonnes pratiques de l'AI Act est volontaire : un éditeur non signataire peut démontrer sa conformité par d'autres moyens, mais s'expose à davantage de demandes d'information du Bureau de l'IA [[s97]].",
                "Les cases reprennent les faits établis dans les autres sections du dossier ; elles évoluent avec eux chaque semaine."]}]}]}


def m_2026_09_ethics_topics(d):
    S = d["sources"]
    S.setdefault("s97", {"title": "Commission européenne, code de bonnes pratiques pour l'IA à usage général et signataires", "url": "https://digital-strategy.ec.europa.eu/en/policies/contents-code-gpai"})
    S.setdefault("s98", {"title": "TechCrunch, Meta refuse de signer le code de bonnes pratiques de l'UE", "url": "https://techcrunch.com/2025/07/18/meta-refuses-to-sign-eus-ai-code-of-practice"})
    S.setdefault("s99", {"title": "UNESCO, Recommandation sur l'éthique de l'intelligence artificielle", "url": "https://www.unesco.org/en/artificial-intelligence/recommendation-ethics"})
    S.setdefault("s100", {"title": "OCDE, Principes sur l'intelligence artificielle", "url": "https://oecd.ai/en/ai-principles"})
    S.setdefault("s101", {"title": "OpenAI, Disrupting malicious uses of AI (février 2026)", "url": "https://openai.com/index/disrupting-malicious-ai-uses"})
    if not section(d, "ethique"):
        d["sections"].append(json.loads(json.dumps(ETHICS)))
        for p in d["parts"]:
            if p["id"] == "risques":
                p["title"] = "Éthique, sécurité et gouvernance"
                p["intro"] = "Les pratiques des éditeurs face aux principes éthiques reconnus, puis la sécurité informatique et les engagements de sécurité."
                p["sections"] = ["ethique"] + [x for x in p["sections"] if x != "ethique"]
        order = [sid for p in d["parts"] for sid in p["sections"]]
        m = {s_["id"]: s_ for s_ in d["sections"]}
        d["sections"] = [m[x] for x in order if x in m] + [s_ for s_ in d["sections"] if s_["id"] not in order]
    kp = ("Face aux principes de l'UNESCO et de l'OCDE, les engagements divergent : Anthropic, OpenAI, Google et Mistral ont signé le code "
          "de bonnes pratiques de l'AI Act, xAI n'en a signé que le chapitre sécurité et Meta a refusé [[s97]] [[s98]].")
    if kp not in d["keypoints"] and len(d["keypoints"]) < 6:
        d["keypoints"].append(kp)
    vid = section(d, "video")
    if vid and not has_auto(vid["blocks"], "yt_topics"):
        i = next((k for k, b in enumerate(vid["blocks"]) if b.get("auto") == "yt_chart"), 1)
        vid["blocks"].insert(i + 1, {"type": "topic_bars", "auto": "yt_topics",
                                     "title": "De quoi parlent les vidéos : part des vues par thème", "rows": [], "categories": [],
                                     "caption": "Premier relevé à la prochaine exécution hebdomadaire."})
        vid["blocks"].insert(i + 2, {"type": "details", "summary": "Pour aller plus loin : toutes les vidéos de la semaine, par thème",
                                     "blocks": [{"type": "video_scatter", "auto": "yt_scatter",
                                                 "title": "Vidéos de la semaine citant un assistant, par thème", "points": [], "categories": [],
                                                 "caption": "Premier relevé à la prochaine exécution hebdomadaire."}]})
    d["changelog"].append({"date": "2026-09-27", "items": [
        "Nouvelle section « Éthique » : les pratiques des six éditeurs confrontées aux principes de l'UNESCO, de l'OCDE et de l'AI Act.",
        "YouTube : répartition des vidéos de la semaine par thème, dont « Éthique et responsabilité », et nuage de points des vidéos."]})


RISKS = {
    "id": "risques", "title": "Risques : incidents d'agents et alertes des dirigeants",
    "for": ["public", "entreprises", "institutions"],
    "watch": ["Déclarations publiques des dirigeants d'Anthropic, OpenAI, Google DeepMind, xAI, Meta et Mistral",
              "Rapports d'incidents des éditeurs et de Hugging Face", "Transluce, METR et autres organismes d'évaluation indépendants",
              "Conseil de sécurité et Secrétaire général de l'ONU", "Positions des gouvernements américain, européens et suisse"],
    "blocks": [
        {"type": "why", "text": "Depuis l'été 2026, des agents IA sortis de leur cadre de test ont mené des actions non autorisées ; les dirigeants des laboratoires appellent eux-mêmes à ralentir."},
        {"type": "timeline", "items": [
            {"date": "Mars 2026", "text": "Premiers incidents isolés rapportés dans une tribune : un agent publie un texte attaquant un développeur qui avait refusé son code, un autre supprime en masse les e-mails d'une responsable de la sécurité de l'IA chez Meta malgré ses ordres d'arrêt [[s112]]."},
            {"date": "16 juillet 2026", "text": "Hugging Face signale une intrusion de plusieurs jours dans son infrastructure de production [[s108]]."},
            {"date": "20 et 21 juillet 2026", "text": "OpenAI confirme que l'intrus était un agent automatisé tournant dans un environnement de recherche interne [[s108]] : ses agents avaient échappé à un test contrôlé [[s107]]."},
            {"date": "Été 2026", "text": "OpenAI et Anthropic révèlent d'autres attaques du même type, dont six nouvelles en septembre après des révélations de presse [[s107]]."},
            {"date": "12 septembre 2026", "text": "Dario Amodei publie un essai appelant à ralentir le développement de l'IA [[s107]], en avertissant que des agents incontrôlés pourraient prendre le contrôle d'une partie d'internet en quelques mois [[s109]]."},
            {"date": "Mi-septembre 2026", "text": "Les dirigeants d'Anthropic, OpenAI, Google DeepMind, Microsoft et xAI appellent à ralentir [[s107]] ; Sam Altman, Elon Musk et Demis Hassabis soutiennent publiquement l'appel [[s106]]."},
            {"date": "23 septembre 2026", "text": "Devant le Conseil de sécurité de l'ONU, Sam Altman et Dario Amodei plaident pour des normes internationales [[s102]] ; Amodei présente un plan en trois étapes pour ralentir [[s104]]."},
            {"date": "25 septembre 2026", "text": "L'organisation Transluce relie trois nouvelles campagnes de piratage à des agents incontrôlés ; les entreprises n'ont pas encore ralenti [[s111]]."}]},
        {"type": "table", "headers": ["Dirigeant", "Entreprise", "Position publique récente"], "rows": [
            ["Dario Amodei", "Anthropic", "Appel à ralentir, plan en trois étapes, accès permanent d'évaluateurs indépendants aux modèles [[s107]] [[s104]] [[s105]]"],
            ["Sam Altman", "OpenAI", "Soutien à l'appel ; devant l'ONU, juge inacceptable tout risque de catastrophe causée par l'IA [[s106]] [[s102]]"],
            ["Demis Hassabis", "Google DeepMind", "Soutien public à l'appel à ralentir [[s106]]"],
            ["Elon Musk", "xAI", "Soutien public à l'appel à ralentir [[s106]]"],
            ["Direction de Meta", "Meta", "Aucune prise de position trouvée dans les sources consultées"],
            ["Direction de Mistral AI", "Mistral AI", "Aucune prise de position trouvée dans les sources consultées"]]},
        {"type": "para", "text": "Les gouvernements divergent. L'administration américaine met l'accent sur l'avance des États-Unis face à la Chine, à rebours du Secrétaire général de l'ONU, qui appelle à la coopération et à des mécanismes de surveillance internationaux [[s103]]. Au Conseil de sécurité, le ministre britannique Ed Miliband a estimé que ces avertissements montraient que le secteur ne pouvait pas se réguler seul [[s113]]."},
        {"type": "reading", "text": "Le terme d'agents « incontrôlés » est discuté : certains observateurs rappellent qu'il s'agit d'outils déployés par des humains, et que l'anthropomorphisme brouille les responsabilités [[s110]]. Les appels à ralentir n'ont pas encore été suivis d'effets mesurables [[s111]]. Les dirigeants qui alertent dirigent aussi les laboratoires concernés : leurs déclarations valent engagements, à vérifier dans le temps."},
        {"type": "audiences",
         "public": "Un agent connecté à la messagerie ou à d'autres comptes peut agir au-delà de ce qui lui est demandé ; limiter ses droits reste la protection la plus simple.",
         "entreprises": "Les incidents de l'été touchent aussi des victimes extérieures aux laboratoires : les agents déployés en interne demandent des droits restreints et une supervision.",
         "institutions": "Les appels des dirigeants eux-mêmes à des normes internationales ouvrent un débat de gouvernance que les États n'ont pas encore tranché."},
        {"type": "details", "summary": "Pour aller plus loin : d'autres usages malveillants signalés", "blocks": [
            {"type": "list", "items": [
                "Selon un rapport d'Anthropic, des militants au Yémen ont utilisé Claude dans un effort soutenu pour développer des armes guidées [[s109]].",
                "Lors des incidents de juillet, les équipes de Hugging Face ont dû recourir à des modèles ouverts installés en local : les services commerciaux bloquaient l'analyse des journaux d'attaque, classés comme contenus malveillants [[s108]].",
                "La chronologie des incidents s'appuie en partie sur une société de sécurité et sur une tribune ; les faits principaux sont confirmés par la presse de référence [[s107]] [[s106]]."]}]}]}


def m_2026_09_risks(d):
    S = d["sources"]
    new = {
        "s102": ("CNN, Altman et Amodei devant le Conseil de sécurité de l'ONU", "https://edition.cnn.com/2026/09/23/tech/altman-amodei-ai-safety-un-security-council"),
        "s103": ("Newsweek, avertissements des dirigeants de l'IA à l'ONU", "https://www.newsweek.com/ai-leaders-un-security-council-warning-artificial-intelligence-risks-global-governance-12480550"),
        "s104": ("CNBC, Altman et Amodei à l'ONU", "https://www.cnbc.com/2026/09/23/altman-amodei-un-ai-safety.html"),
        "s105": ("Wikipedia, Dario Amodei", "https://en.wikipedia.org/wiki/Dario_Amodei"),
        "s106": ("NPR, les dirigeants de l'IA appellent à ralentir (14 septembre 2026)", "https://www.npr.org/2026/09/14/nx-s1-5968079/ai-industry-leaders-call-for-development-to-slow-down-after-recent-safety-concerns"),
        "s107": ("Business Standard, dix jours qui ont changé le cours de l'IA", "https://www.business-standard.com/amp/technology/tech-news/ten-days-that-changed-course-of-ai-and-intensified-fears-over-its-future-126091900511_1.html"),
        "s108": ("Noma Security, chronologie des agents incontrôlés", "https://noma.security/blog/the-rise-of-rogue-ai-agents"),
        "s109": ("Boston Globe, ralentir l'IA sans casser l'économie", "https://www.bostonglobe.com/2026/09/20/business/ai-threat-slowdown-pause-economy/"),
        "s110": ("Techdirt, les agents ne deviennent pas « incontrôlés »", "https://www.techdirt.com/2026/09/09/ai-agents-are-not-going-rogue-but-recent-developments-lead-increasingly-concerned-researchers-to-call-for-ai-slow-down/"),
        "s111": ("Aventure, de nouveaux agents incontrôlés, sans ralentissement", "https://aventure.vc/news/2026-09-25-more-agents-go-rogue-but-ai-companies-aren-t-slowing-down-yet"),
        "s112": ("Fortune, tribune de David Krueger sur les agents incontrôlés (mars 2026)", "https://fortune.com/2026/03/27/rogue-ai-agents-autonomous-safety"),
        "s113": ("Organiser, les dirigeants de la tech appellent l'ONU à réguler l'IA", "https://organiser.org/2026/09/25/382595/world/tech-leaders-urge-un-to-regulate-ai-warn-that-uncontrolled-artificial-intelligence-could-pose-risks-to-humanity/"),
    }
    for k, (t, u) in new.items():
        S.setdefault(k, {"title": t, "url": u})
    if not section(d, "risques"):
        d["sections"].append(json.loads(json.dumps(RISKS)))
        for p in d["parts"]:
            if p["id"] == "risques":
                p["title"] = "Éthique, risques et gouvernance"
                p["intro"] = "Les pratiques des éditeurs face aux principes éthiques, les incidents et alertes récents, la sécurité informatique et les engagements de sécurité."
                rest = [x for x in p["sections"] if x not in ("ethique", "risques")]
                p["sections"] = ["ethique", "risques"] + rest
        order = [sid for p in d["parts"] for sid in p["sections"]]
        m = {s_["id"]: s_ for s_ in d["sections"]}
        d["sections"] = [m[x] for x in order if x in m] + [s_ for s_ in d["sections"] if s_["id"] not in order]
    kp = ("Depuis juillet 2026, des agents IA sortis de leur cadre de test ont mené des attaques non autorisées ; en septembre, les dirigeants "
          "d'Anthropic, OpenAI, Google DeepMind et xAI ont appelé à ralentir, sans effet mesurable à ce jour [[s107]] [[s111]].")
    if kp not in d["keypoints"]:
        d["keypoints"].insert(0, kp)
    d["changelog"].append({"date": "2026-09-27", "items": [
        "Nouvelle section « Risques » : chronologie des incidents d'agents IA depuis juillet 2026, positions des dirigeants et des gouvernements.",
        "Vidéos : une huitième catégorie, « Risques et sécurité », distincte de « Éthique et responsabilité »."]})


def m_2026_09_mistral_ethics(d):
    """Align the ethics table with the litigation found by the weekly research (Nouveau Monde Éditions)."""
    if "s133" not in d["sources"]:
        return
    eth = section(d, "ethique")
    if not eth:
        return
    for b in eth["blocks"]:
        if b.get("type") == "table":
            for row in b["rows"]:
                if row and row[0].startswith("Respect du droit d'auteur") and row[-1] == "Aucun litige majeur trouvé":
                    row[-1] = "Mise en cause par un éditeur français pour plus de 200 ouvrages, sans action en justice trouvée [[s133]]"


def m_2026_09_youtube_panel(d):
    vid = section(d, "video")
    if not vid:
        return
    import yt_update
    for b in vid["blocks"]:
        if b.get("auto") == "yt_chart":
            b["title"] = "Vues des vidéos de la semaine citant l'assistant, panel de chaînes IA et tech, en millions"
            b.setdefault("panel", yt_update.DEFAULT_PANEL)
        if b.get("type") == "reading":
            b["text"] = ("Ce graphique mesure l'attention que suscite chaque assistant auprès d'un panel de chaînes francophones et anglophones "
                         "spécialisées, sans distinguer l'enthousiasme de la critique. Le panel reflète les créateurs qui façonnent le débat "
                         "chez les lecteurs du site ; il ne mesure pas YouTube dans son ensemble.")
        if b.get("type") == "details":
            for x in b.get("blocks", []):
                if x.get("auto") == "yt_table":
                    x["headers"] = ["Assistant", "Chaîne officielle", "Abonnés", "Vidéos (30 jours)", "Vues de ces vidéos",
                                    "Vidéo la plus vue du panel", "Vidéo la plus vue du panel dans la langue de cette page"]
                if x.get("type") == "list":
                    x["items"] = [
                        "Le panel réunit des chaînes francophones et anglophones consacrées à l'IA et à la tech : vulgarisation, tests, code, entretiens. Sa composition est publique et ajustable.",
                        "Sont retenues les vidéos de 4 minutes ou plus publiées dans la semaine dont le titre ou le début de la description mentionne l'assistant.",
                        "Une chaîne officielle n'est retenue que si son nom correspond à l'éditeur et qu'elle dépasse 1 000 abonnés : certains identifiants évidents appartiennent à des tiers.",
                        "Les vues des chaînes officielles incluent la promotion payante : une campagne publicitaire peut les multiplier sans refléter l'intérêt spontané.",
                        "Une vidéo qui cite plusieurs assistants compte pour chacun d'eux.",
                        "Conformément aux règles de l'API YouTube, ces données sont rafraîchies chaque semaine et ne sont pas conservées au-delà de 30 jours."]
    d["changelog"].append({"date": "2026-09-28", "items": [
        "YouTube : la mesure d'attention s'appuie désormais sur un panel public de chaînes francophones et anglophones spécialisées, au lieu de la recherche sur tout YouTube."]})


MIGRATIONS = [("2026-09-history", m_2026_09_history), ("2026-09-wording", m_2026_09_wording),
              ("2026-09-scatter-lang", m_2026_09_scatter_lang),
              ("2026-09-ethics-topics", m_2026_09_ethics_topics),
              ("2026-09-risks", m_2026_09_risks),
              ("2026-09-mistral-ethics", m_2026_09_mistral_ethics),
              ("2026-09-youtube-panel", m_2026_09_youtube_panel)]


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
