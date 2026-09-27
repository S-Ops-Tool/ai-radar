# Radar des assistants IA

Dossier comparatif public (Claude, ChatGPT, Gemini, Grok, Muse, Mistral Vibe), mis à jour chaque semaine et publié sur GitHub Pages.

## Fonctionnement

1. Chaque lundi à 04:00 UTC, `weekly-update.yml` lance d'abord `scripts/data_update.py`, qui met à jour les graphiques chiffrés directement depuis Epoch AI (centres de données) et Vectara (hallucinations), sans modèle de langage.
2. `scripts/update.py` prend le relais : pour chaque section, Claude part de la liste de sources primaires suivies (`watch`), effectue des recherches web et renvoie la section mise à jour au format JSON. Les blocs portant une clé `auto` et la liste `watch` sont restaurés à l'identique après chaque réponse.
3. Le script valide chaque réponse : structure inchangée, types de blocs connus, références existantes, et toute nouvelle source doit provenir des recherches réellement effectuées. Une section qui échoue garde sa version précédente.
4. Un brief de la semaine est écrit dans `content/briefs/AAAA-MM-JJ.md` et une entrée est ajoutée au journal des mises à jour.
5. Par défaut, les changements arrivent sous forme de pull request, avec le brief comme description. La fusion déclenche la publication.

## Réglages (Settings > Secrets and variables > Actions)

| Nom | Type | Rôle | Défaut |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | secret | clé API Anthropic | obligatoire |
| `AUTO_PUBLISH` | variable | `true` publie sans relecture | `false` |
| `CLAUDE_MODEL` | variable | modèle utilisé | `claude-opus-5-5` |
| `MAX_SEARCHES_PER_SECTION` | variable | plafond de recherches par section | `6` |

## Fichiers

- `content/dossier.json` : tout le contenu (matrice, sections, graphiques, sources, journal).
- `scripts/data_update.py` : données chiffrées depuis les jeux de données d'origine.
- `content/data_state.json` : modèles déjà vus au classement Vectara, pour signaler les nouveaux.
- `scripts/update.py` : mise à jour rédactionnelle via l'API Claude.
- `scripts/build.py` : génère `site/index.html`, sans dépendance externe.
- `scripts/style.css`, `scripts/pipeline.svg` : mise en forme et schéma fixe.

## Coût

Neuf sections, au plus six recherches chacune, plus un appel pour la matrice. Le coût dépend du modèle et des tarifs en vigueur : il se suit dans la console Anthropic. Passer `CLAUDE_MODEL` sur un modèle Sonnet le réduit nettement.

## Lancer à la main

Onglet Actions > Mise à jour hebdomadaire > Run workflow. Le champ facultatif limite la mise à jour à certaines sections, par exemple `cyber,calcul`.

Identifiants de sections : `donnees`, `biais`, `precision`, `tempsreel`, `agents`, `cyber`, `calcul`, `energie`, `gouvernance`.

## Choisir les modèles du graphique Vectara

Le bloc `vectara_hhem` de la section `precision` liste un modèle par éditeur (`models`). Quand un éditeur publie un nouveau modèle phare et qu'il entre au classement, le brief de données le signale ; il suffit alors de remplacer l'identifiant correspondant dans `content/dossier.json`.
