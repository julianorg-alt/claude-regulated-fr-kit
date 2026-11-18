# Plan de sortie du fournisseur de modèles

Backlog E10.2. Ce plan répond à l’article 28, paragraphes 7 et 8, du règlement (UE) 2022/2554 (DORA) et à l’article 30, paragraphe 3, point f, lu dans le texte du Journal officiel (constat V67). Il vaut pour un service d’inférence qui soutient une fonction critique ou importante ; pour les autres, il sert de base proportionnée. Les valeurs entre crochets sont à fixer par l’entité financière : le kit ne connaît ni ses fonctions, ni ses délais, ni son contrat.

Le plan décrit ce que le kit permet de faire techniquement et ce qui reste une décision de l’entité. Il ne remplace ni le contrat, ni le registre d’informations (`docs/compliance/modeles/registre-dora.md`).

## 1. Périmètre et déclencheurs

Fournisseur concerné : le fournisseur du modèle, Anthropic par Amazon Bedrock dans le chemin par défaut du kit. Les cas qui déclenchent l’examen d’une sortie reprennent l’article 28, paragraphe 7, et l’article 28, paragraphe 8 :

| Déclencheur | Origine | Qui décide |
|---|---|---|
| Défaillance prolongée du fournisseur ou d’une région d’inférence | Art. 28 §8 (défaillance) | [Responsable de la fonction et RSSI] |
| Dégradation de la qualité mesurée par la suite d’évaluation | Art. 28 §8 (qualité) | [Responsable de la fonction] |
| Violation grave, faiblesses avérées, circonstances révélées par le suivi des risques | Art. 28 §7 a à c | [Direction, après avis du délégué à la protection des données] |
| L’autorité ne peut plus surveiller l’entité efficacement | Art. 28 §7 d | [Direction et conformité] |
| Changement de sous-traitant ou de lieu de traitement jugé inacceptable (délai d’objection court, voir la grille DPA et DORA) | Contrat | [Conformité] |
| Retrait d’un modèle ou changement de ses conditions | Suivi du fournisseur | [Responsable de la fonction] |

Un seul de ces cas suffit pour ouvrir l’examen. La bascule elle-même reste une décision humaine : le kit ne bascule jamais seul (voir la section 3).

## 2. Solutions alternatives

| Solution | Ce que le kit fournit | Ce qui reste à faire |
|---|---|---|
| Autre région UE d’Amazon Bedrock (même fournisseur) | `--fallback-region` dans le générateur de configuration, profils `eu.` de l’inventaire | Ne couvre pas la défaillance du fournisseur lui-même ni sa résiliation. |
| Mistral AI par son API | Entrée `mistral` de `infra/inventory/exit-providers.json`, schéma OpenAI, clé injectée à l’exécution | Contrat et DPA lus (V66 : lieu d’hébergement non nommé, sous-traitants non lus), ajout au registre, analyse des transferts, identifiants de modèles, mesure de qualité. |
| OpenGateLLM, auto-hébergé | Entrée `opengatellm` de l’inventaire, hôte fourni par l’exploitant | Hébergement et exploitation des modèles, projet signalé en bêta (V66). |
| Solution interne | Aucune : la passerelle accepte tout service compatible OpenAI sous l’inventaire | Choix et exploitation du modèle. |
| Vertex « eu » | Reporté après la v1 (backlog E13) | Tout. |

Ajouter un fournisseur à l’inventaire est une décision : elle passe par la mise à jour du registre DORA, de l’analyse des transferts et de la grille d’écarts du contrat, avant la fusion du changement.

## 3. Procédure de bascule

Deux modes, tous deux produits par `tools/crfr/gateway_config.py` (option `--exit-mode`) :

- `standby` : des alias `exit-<alias>` s’ajoutent aux routes existantes, réservés au groupe qui fait les exercices (politique OPA). Ils servent à rejouer la suite d’évaluation et à mesurer l’écart sans toucher au trafic.
- `switch` : les alias de production eux-mêmes pointent vers le second fournisseur. Les clients ne changent rien.

Il n’y a pas de secours automatique vers un autre fournisseur, et le test `test_no_automatic_failover_to_another_provider` l’interdit : un changement de sous-traitant modifie le registre, le contrat applicable et les transferts, il ne se décide pas dans une règle de reprise sur erreur. Le secours automatique entre deux régions du même fournisseur reste possible (`--fallback-region`).

Étapes :

1. Décision datée, avec le déclencheur retenu et la personne qui décide.
2. Vérifier que le second fournisseur est dans l’inventaire, que son contrat est signé et qu’il figure au registre.
3. Générer la configuration en mode `switch` avec les identifiants de modèles choisis (`--exit-model alias=modèle`) et revoir la différence avec la configuration en place.
4. Fournir la clé du second fournisseur à la passerelle par le secret `exit-provider-credentials` (variable `EXIT_PROVIDER_API_KEY` au démarrage), jamais dans un fichier.
5. Déployer. La pseudonymisation, la politique, les quotas et le journal d’audit s’appliquent au même titre (contrôle C21, tests de bout en bout).
6. Rejouer la suite d’évaluation (section 5) sur les alias de production et conserver le résultat avec la décision.
7. Surveiller le journal d’audit et les budgets : les prix du fichier `gateway/config/guard.json` sont ceux du démonstrateur, à remplacer par ceux du second contrat.
8. Retour arrière : régénérer la configuration en mode `standby` ou sans second fournisseur et redéployer.

## 4. Données : restituer, supprimer, conserver

| Donnée | Où | Sortie |
|---|---|---|
| Invites et réponses | Chez le fournisseur, selon sa conservation | Le DPA d’Anthropic prévoit restitution et suppression sous trente jours après la fin (V45, grille DPA et DORA). Demander l’attestation de suppression. Pour un second fournisseur : lire son DPA (V66 : accès coupé trente jours après la fin de l’accès, ZDR à confirmer). |
| Journal d’audit | Compartiment WORM de l’entité | Reste chez l’entité, durée du module `gateway-audit-store` (contrôle C10). Rien à restituer. |
| Journal de contenu pseudonymisé | Chez l’entité, quelques jours | Idem ; ne contient que ce que le fournisseur a vu (C12). |
| Correspondances de pseudonymes | Coffre de la passerelle, durée de vie courte | Chez l’entité, hors journaux. Une bascule ne les déplace pas. |
| Configuration, politiques, jeu d’évaluation | Dépôt de l’entité | Réutilisables tels quels : aucune API propre au fournisseur n’est exigée des clients. |

Aucun jeu de données n’est stocké chez le fournisseur par le kit au-delà de ce que prévoit son contrat. Les fonctions propres au fournisseur (par exemple l’inférence avec cache de prompt) ne sont pas reproduites par un second fournisseur : l’usage du cache est donc une dépendance à inventorier par application.

## 5. Mesure de l’écart de qualité

Le plan doit être « soumis à des tests suffisants » (art. 28 §8). Ce que l’exercice du kit prouve et ce qu’il ne prouve pas :

- Prouvé par `make exit-drill` et par les tests de bout en bout : la bascule se fait sans changement côté client, aucune requête n’atteint plus Bedrock pour les alias basculés, les contrôles s’appliquent et le décompte des jetons fonctionne, y compris en flux (constat V65).
- Non prouvé : la qualité des réponses d’un vrai second modèle. Les cassettes de la suite d’évaluation sont des réponses de référence écrites à la main (`evals/README.md`) ; les rejouer sur le second fournisseur ne mesurerait que le kit. Le faux fournisseur du démonstrateur répète la question et ne dit rien de la qualité.

Mesure à faire avec une clé du second fournisseur, hors CI (décision K8) :

1. `make eval-live` avec le fournisseur d’origine, puis `make eval-record` si l’on veut figer une référence.
2. `make eval-live` avec le second fournisseur (variable `EVAL_PROVIDER`, par exemple `mistral:mistral-large-4-0` : promptfoo 0.125.1 a ce fournisseur, V75). Un modèle qui raisonne toujours demande un `max_tokens` plus grand et l’écart du bloc de raisonnement : voir `evals/promptfooconfig.mistral.yaml`.
3. `make eval-compare OLD=<référence> NEW=<second fournisseur>` : l’outil échoue si une tâche manque, si une tâche critique qui passait échoue ou si le taux de réussite baisse.
4. Consigner dans le tableau ci-dessous, avec la date, les modèles, la valeur de k et la liste des régressions, même non critiques.

| Date | Référence | Second fournisseur | Taux de réussite | Tâches critiques | Décision |
|---|---|---|---|---|---|
| 18/11/2026 | Claude Sonnet 5.5, run 5 (k = 3, juge Opus 5.5) | Mistral Large 4 (`mistral-large-4-0`, V75), même invite, mêmes tâches, `max_tokens` 16384 et bloc de raisonnement écarté de la réponse | Jeu principal : 0,9356 contre 0,9957 ; jeu de réserve : 0,9167 contre 0,9667 | Jeu principal : 0,75 contre 1,00 (6 tâches critiques en échec : assurance-08, public-04, public-12, sante-07, sante-12, sante-13) ; jeu de réserve : 0,80 contre 0,90 | Seuil du kit non atteint (critiques en régression). Décision de bascule à l’entité. Détail et réserves : `docs/evals/exit-provider-2026-11-18.md`. Avec le réglage par défaut de promptfoo, 111 réponses sur 300 sont coupées dans le raisonnement (taux 0,5489) : à traiter avant toute bascule. |

Seuil d’acceptation de la bascule : [à fixer par l’entité ; le seuil du kit pour l’évaluation réelle est de 0,9 de réussite avec k répétitions, aucune tâche critique en régression].

## 6. Tests et réexamen

- À chaque version du kit : `make test` (configuration, faux fournisseur) et `make e2e` puis `make exit-drill` dans la CI.
- [Au moins une fois par an] : exercice avec un vrai second fournisseur, mesure de qualité de la section 5, mise à jour du tableau, relecture de ce plan et du registre.
- Après tout changement de contrat ou de sous-traitant : relire les sections 2 et 4.
- Le contrat doit prévoir la période de transition obligatoire de l’article 30, paragraphe 3, point f. Le DPA d’Anthropic n’en contient pas ; elle dépend de l’accord principal, non analysé ici (grille DPA et DORA).

## 7. Limites et points ouverts

- Hébergement, sous-traitants et ZDR de Mistral AI non vérifiés (V66) : tant qu’ils le restent, la résidence UE d’une sortie vers ce fournisseur n’est pas établie.
- Appels d’outils et images : la traduction de Messages vers le schéma OpenAI n’a été constatée que sur des messages texte (V65). Claude Code et les agents en dépendent : à constater avant d’annoncer une sortie équivalente.
- Écart de qualité mesuré le 18/11/2026 sur un seul modèle (Mistral Large 4) et une seule passe : voir le tableau de la section 5 et `docs/evals/exit-provider-2026-11-18.md`. Il ne vaut pas pour un autre modèle ni pour une invite écrite pour lui.
- Les identifiants de modèles du second fournisseur sont laissés à l’exploitant (celui de Mistral Large 4 est constaté en V75).
- Ce plan couvre la sortie technique. Les scénarios de faillite du fournisseur, de résolution de l’entité (art. 30 §3 f, i) et le calendrier de migration des applications relèvent de l’entité.
