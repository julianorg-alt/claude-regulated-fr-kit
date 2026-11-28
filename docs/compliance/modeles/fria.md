# Modèle de FRIA : analyse d’impact sur les droits fondamentaux

> **English summary.** Template for a fundamental rights impact assessment under article 27 of the EU AI Act. The obligation falls on the deployer; classifying a use as high-risk is for the deployer to establish, and this template does not presume it. Check the consolidated version of the article before use.

Règlement IA (UE) 2024/1689, article 27, dans sa version publiée au Journal officiel (constat V42). Une version modifiée de l’article circule sur des sites secondaires ; tant que l’acte modificatif n’est pas identifié, vérifier la version consolidée avant usage. Utiliser aussi le modèle de questionnaire que le Bureau de l’IA doit publier (paragraphe 5).

## Qui doit la faire

L’obligation pèse sur le déployeur, avant le premier déploiement d’un système d’IA à haut risque au sens de l’article 6, paragraphe 2 (hors domaine du point 2 de l’annexe III), lorsque ce déployeur est un organisme de droit public ou une entité privée fournissant des services publics, ainsi que sur les déployeurs des systèmes visés aux points 5 b) et c) de l’annexe III. La classification d’un usage comme « à haut risque » est à établir par le déployeur au regard de l’annexe III ; ce modèle ne la présume pas.

Un assistant de rédaction ou de résumé derrière la passerelle du kit n’est pas, par lui-même, un système à haut risque. Il peut le devenir selon l’usage qu’on en fait : c’est l’usage qu’il faut décrire ci-dessous. Une AIPD (modèle `aipd.md`) peut déjà remplir une partie de ces obligations ; la FRIA la complète alors (paragraphe 4).

| Champ | Valeur |
|---|---|
| Déployeur | [Un organisme public, par exemple] |
| Système d’IA et fournisseur | [Nom du système, version, fournisseur ; modèle sous-jacent] |
| Usage à haut risque visé | [Point de l’annexe III, à justifier] |
| Version et date | [v1, JJ/MM/AAAA] |

## a) Processus dans lesquels le système est utilisé

[Décrire le processus métier du déployeur où le système intervient, conformément à sa destination : étapes, qui reçoit la sortie, quelle décision elle prépare.]

## b) Période et fréquence d’utilisation

[Période prévue, volume et fréquence d’appels. La passerelle mesure les appels par utilisateur, équipe et application (C07) et les trace sans contenu (C10, C13) : ces chiffres servent de base.]

## c) Catégories de personnes et groupes concernés

[Personnes physiques et groupes susceptibles d’être concernés dans ce contexte, y compris les personnes vulnérables.]

## d) Risques spécifiques de préjudice

[Risques pour les catégories identifiées en c), en tenant compte des informations fournies par le fournisseur au titre de l’article 13.]

Éléments que le kit permet de documenter :
- Les résultats de l’évaluation en français, les tâches critiques et les régressions à chaque changement de modèle (C14, `evals/README.md`).
- Le refus de conseil personnalisé et de décision individuelle fait partie des tâches critiques de cette évaluation ; un échec bloque la mise en service.

## e) Mesures de contrôle humain

[Décrire la mise en œuvre du contrôle humain conformément à la notice d’utilisation du fournisseur : qui relit, avec quel pouvoir de modifier ou d’écarter la sortie, comment l’utilisateur est formé.]

Mesures techniques du kit à mentionner : coupure d’urgence à trois niveaux (C08), autorisation par groupe (C02), journal d’audit qui relie chaque sortie à un appelant (C10).

## f) Mesures en cas de matérialisation des risques

[Gouvernance interne, mécanisme de plainte interne, procédure de suspension, responsable désigné.]

## Notification

Le déployeur notifie (paragraphe 3) les résultats à l’autorité de surveillance du marché, en joignant le modèle de l’AI Office rempli ; l’analyse est mise à jour lorsqu’un élément des points a) à f) change (paragraphe 2). Le paragraphe 3 prévoit une exemption de notification dans le cas de l’article 46, paragraphe 1. Dates : le texte publié au JO rend le règlement applicable au 2 août 2026, et l’article 6, paragraphe 1, au 2 août 2027 (article 113) ; un report pour l’annexe III au 2 décembre 2027 est affiché par des sources secondaires, sans acte modificatif identifié à ce jour (V42). L’autorité de surveillance du marché compétente en France reste à désigner dans ce modèle : [à compléter].

| Étape | Qui | Date |
|---|---|---|
| Analyse validée | [fonction] | [ ] |
| Notification à l’autorité | [fonction] | [ ] |
| Prochaine revue | | [ ] |
