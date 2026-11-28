# Passation maître : projets vitrines de la candidature

État au 28/11/2026. Inventaire fait par lecture (sous-agents Haiku), sans exécution des tests : tout "non vérifié" l'est réellement.

Règles : dépôts publics sans fusion par l'API, commit anonyme, aucun nom de client ni donnée interne ni secret ni info personnelle, relecture Opus avant toute publication. Rien n'est envoyé à Anthropic ni à un tiers : brouillons seulement. Aucun fait, chiffre ou expérience inventé dans un texte de candidature : `[À COMPLÉTER]`.

## Projets

| Projet | Dépôts | But | État | Manques pour être présentable |
|---|---|---|---|---|
| regulated-fr | privé + `claude-regulated-fr-kit` (public) | Kit de référence pour déployer Claude en organisation réglementée française : passerelle, pseudonymisation FR, gouvernance agents/MCP, évaluation en français, conformité reliée aux tests. v0.8.0 | README anglais complet, CI (lint, tests, secrets, e2e, exit drill, redteam hebdo), Apache 2.0, 0 PR ouverte. Public en retard d'un commit sur le privé (21/11 contre 22/11) | `make demo` et `make ci` à rejouer sur clone propre ; relier chaque chiffre du README à un script ; cassettes d'éval écrites à la main et redteam sur faux modèle (déjà dit, à garder visible) ; `SECURITY.md` trop court ; textes de conformité en français seulement |
| ai-roi-value-case | privé + `ai-roi-value-case-public` | Calculateur de ROI d'un déploiement IA (page statique) et modèle de dossier de valeur, FR/EN | README bilingue, tests (47 + 21 annoncés, non relancés), CI avec scan de secrets, MIT, 0 PR ouverte. Public : 2 commits | Un seul exemple chiffré (2 mesures réelles) ; pas d'URL de démo dans le README ; l'auteur du dernier commit public porte une adresse personnelle (historique à réécrire : décision de l'auteur) ; historique public non scanné |
| boamp-llm-eval | privé + `boamp-llm-eval-public` | Benchmark reproductible Haiku/Sonnet/Opus 5.5 sur l'extraction de 9 champs d'avis BOAMP | README FR/EN, CI (ruff, pytest, secrets), MIT code + Licence Ouverte données. Public plus avancé (v2, 500 avis) ; privé a 1 PR brouillon (CI runner). Dépôts divergés | Écarts dev (0,852 / 0,864 / 0,917) avec intervalles qui se recouvrent : à formuler prudemment ; v2 absente du privé (réaligner) ; `docs/HANDOFF-v2.md` du public contient un terme interne à retirer ; données `data/*.jsonl` non scannées pour noms/e-mails |
| mcp-dpe-fr | `mcp-dpe-fr` (public) | Serveur MCP lecture seule sur les DPE ADEME, 6 outils agrégés, sans clé API | README anglais clair, CI 3 versions Python + ruff + replay + dérive API hebdo, publication PyPI par OIDC prévue, MIT. 1 seul commit (0.1.0) | Pas encore publié sur PyPI (à vérifier) ; pas de démo (capture, exemple de sortie) ; 19 questions en replay, aucune mesure de qualité ; HTTP sans authentification (documenté) |

## Points transverses

- Avant tout export public : relancer le contrôle des termes interdits côté privé (le script d'export le fait) et le contrôle d'identité des commits.
- Statut CI des derniers commits : non vérifié sur les 7 dépôts.
- Clés `AKIA…` dans le kit : valeurs fictives de test, pas de secret repéré (contrôle partiel).

## Prochaines actions (proposées, ordre soumis à l'auteur par QCM)

1. Vérification : rejouer tests et démo sur clones propres, statut CI, scan d'historique des dépôts publics.
2. Réaligner privé/public (kit en retard, boamp divergé) et corriger l'identité du dernier commit public ROI.
3. Mesures : dossier de preuves chiffré par projet (chaque chiffre relié à un script).
4. Démo et lisibilité : URL ou capture par projet, `SECURITY.md`, résumé anglais en tête de chaque README.
5. Publication mcp-dpe-fr sur PyPI (après relecture).
6. Brouillons de candidature (CV, lettre, page de synthèse des 4 projets) : `[À COMPLÉTER]` pour tout fait non documenté. Envoi par l'auteur seul.

## Sous-sessions actives

Aucune pour l'instant.
