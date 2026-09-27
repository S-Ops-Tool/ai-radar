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
- `scripts/aa_update.py` : indice d'intelligence, prix et vitesse des modèles (API Artificial Analysis, secret `ARTIFICIAL_ANALYSIS_API_KEY`).
- `scripts/yt_update.py` : chaînes officielles et attention sur YouTube (YouTube Data API v3, secret `YOUTUBE_API_KEY`, environ 650 unités de quota par semaine).
- `scripts/hn_update.py` : articles Hacker News par assistant (API Algolia, sans clé), avec historique hebdomadaire dans `content/data_state.json`.
- `scripts/status_update.py` : incidents déclarés sur les pages de statut des éditeurs, accumulés dans `content/data_state.json`.
- `content/data_state.json` : modèles déjà vus au classement Vectara, pour signaler les nouveaux.
- `scripts/update.py` : mise à jour rédactionnelle via l'API Claude.
- `scripts/build.py` : génère `site/index.html`, sans dépendance externe.
- `scripts/style.css`, `scripts/pipeline.svg` : mise en forme et schéma fixe.

## Coût

Neuf sections, au plus six recherches chacune, plus un appel pour la matrice. Le coût dépend du modèle et des tarifs en vigueur : il se suit dans la console Anthropic. Passer `CLAUDE_MODEL` sur un modèle Sonnet le réduit nettement.

## Lancer à la main

Onglet Actions > Mise à jour hebdomadaire > Run workflow. Le champ facultatif limite la mise à jour à certaines sections, par exemple `cyber,calcul`.

Identifiants de sections : `usages`, `perception`, `video`, `acteurs`, `capacites`, `precision`, `disponibilite`, `tempsreel`, `agents`, `prix`, `confidentialite`, `donnees`, `biais`, `cyber`, `gouvernance`, `calcul`, `energie`.

## Graphique Vectara : modèles testés et derniers modèles phares

Le bloc `vectara_hhem` de la section `precision` contient, pour chaque éditeur (`vendors`) :

- `prefix` : le préfixe des identifiants Vectara de l'éditeur ; tous ses modèles au classement apparaissent en points gris ;
- `tested` : le modèle mis en avant, avec sa date de sortie et sa source (`date: null` s'affiche « date non vérifiée ») ;
- `latest` : le dernier modèle phare de l'éditeur, avec date et source ; `id` est renseigné quand ce modèle figure au classement.

Le script de données calcule l'écart en mois et signale les nouveaux modèles entrés au classement. L'étape hebdomadaire de Claude peut remplacer `latest` quand un nouveau modèle phare sort, à condition de fournir une date valide et une source existante. Le choix du modèle `tested` reste manuel, à partir des signalements du brief de données.

## Structure du contenu

- `keypoints` : les constats clés en tête de page, révisés par l'étape matrice quand les changements de la semaine le justifient.
- `profiles` : les trois profils de lecture (grand public, entreprises, institutions) ; chaque section porte un champ `for` qui détermine où elle apparaît quand un profil est sélectionné.
- `parts` : les cinq parties et l'ordre des sections.
- Blocs : `why` (pourquoi le sujet compte), `audiences` (une phrase par public), `details` (approfondissement dépliable, un seul niveau).
- `glossary` : le glossaire, maintenu à la main.
