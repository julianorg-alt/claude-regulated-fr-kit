# Grille d’écarts : DPA d’Anthropic et article 30 de DORA

> **English summary.** Gap grid comparing Anthropic's Data Processing Addendum (in force 24 February 2025) with the minimum contractual provisions of DORA article 30. It applies to direct Anthropic API use only; for Amazon Bedrock, the default path of the kit, the AWS contract applies and has not been read here. "Absent from the DPA" does not mean "absent from the contract".

Backlog E9.3. La grille compare le Data Processing Addendum d’Anthropic, en vigueur le 24 février 2025 (constat V45), aux dispositions contractuelles minimales de l’article 30 du règlement (UE) 2022/2554, lu dans sa version publiée au Journal officiel (constat V44).

## Quel contrat est concerné

- Par Amazon Bedrock, chemin par défaut du kit : le contrat de services TIC est celui d’AWS, pas celui d’Anthropic. Cette grille ne s’applique pas telle quelle ; il faut refaire l’exercice avec l’accord client AWS et son avenant de traitement, qui n’ont pas été lus.
- Par l’API Anthropic directe (évaluations `make eval-live`, ou un déploiement qui l’utiliserait) : le DPA d’Anthropic s’applique, intégré aux conditions commerciales (V38). Le DPA renvoie à l’accord principal pour la résiliation, les niveaux de service et la responsabilité ; ces conditions n’ont pas été analysées ici. « Absent du DPA » ne veut donc pas dire « absent du contrat ».

## Grille

| DORA, art. 30 | Exigence (résumé) | DPA d’Anthropic | Écart |
|---|---|---|---|
| 2 a) | Description des fonctions et services ; sous-traitance permise et conditions | C.1 : autorisation générale des sous-traitants de l’annexe 4 ; C.3 b) : objection possible dans les 15 jours suivant l’avis d’un nouveau sous-traitant, sinon consentement réputé | Partiel : pas de description des fonctions ; délai d’objection court |
| 2 b) | Lieux de prestation et de traitement, y compris de stockage ; préavis de changement | Annexe 3 : clauses types UE (modules 2 et 3), avenants britannique et suisse ; lieux non précisés | Écart : ni régions ni pays de traitement, pas de préavis de changement de lieu |
| 2 c) | Disponibilité, authenticité, intégrité, confidentialité des données | E.1 et annexe 2 : mesures techniques et organisationnelles « reasonable and appropriate » | Couvert sur le principe ; à apprécier au regard de l’annexe 2 |
| 2 d) | Accès, récupération et restitution des données en cas d’insolvabilité, de résolution, d’arrêt d’activité ou de fin de contrat | H.1 : restitution d’une copie sur demande et suppression dans les 30 jours suivant la fin de l’accord | Partiel : fin de contrat seulement ; insolvabilité et résolution non traitées ; format non précisé |
| 2 e) | Description des niveaux de service | Rien dans le DPA | Absent du DPA, à chercher dans l’accord principal |
| 2 f) | Assistance en cas d’incident TIC, sans coût ou à coût fixé d’avance | G.1 : notification d’une violation de données « within 48 hours » | Partiel : vise les violations de données personnelles, pas tout incident TIC ; coût non fixé |
| 2 g) | Coopération pleine avec les autorités compétentes et de résolution | B.6 : assistance au client pour l’AIPD et la consultation préalable | Écart : pas d’engagement de coopération directe avec les autorités financières |
| 2 h) | Droits de résiliation et préavis minimaux | Rien dans le DPA (H.1 ne traite que l’après-résiliation) | Absent du DPA, à chercher dans l’accord principal |
| 2 i) | Participation aux programmes de sensibilisation et de formation de l’entité | C.2 : formation interne des employés d’Anthropic | Écart |
| 3 a) | Niveaux de service complets avec objectifs quantitatifs et qualitatifs | Rien dans le DPA | Absent du DPA |
| 3 b) | Préavis et obligation d’informer de tout développement à impact significatif | B.4 : information si Anthropic ne peut plus respecter ses obligations de traitement ; G.1 | Partiel |
| 3 c) | Plans de continuité mis en œuvre et testés ; mesures de sécurité TIC | Annexe 2, A.4 : plan de continuité « tested annually » | Couvert sur le principe |
| 3 d) | Participation aux tests de pénétration fondés sur la menace (TLPT, art. 26 et 27) | G.2 : résumé du dernier rapport de test d’intrusion sur demande | Écart |
| 3 e) | Accès, inspection et audit sans restriction, par l’entité et par l’autorité ; copies sur place | F.1 à F.4 : rapports d’audit tiers (par exemple SOC 2) « to the extent available » ; audit par le client à ses frais, d’accord commun, au plus une fois par période de 12 mois sauf non-conformité ou demande d’une autorité de contrôle | Écart : droits limités, rien sur les autorités financières ni le superviseur principal |
| 3 f) | Stratégie de sortie avec période de transition obligatoire | H.1 : restitution et suppression | Écart : pas de période de transition (voir backlog E10.2, plan de sortie) |

Les points 3 a) à 3 f) ne s’imposent que si le service soutient une fonction critique ou importante.

## Rétention à signaler au comité des risques

- Hors ZDR, l’API Anthropic supprime entrées et sorties sous 30 jours, sauf exceptions : les contenus signalés par les filtres de sécurité sont gardés jusqu’à 2 ans, les scores de classification jusqu’à 7 ans (V38).
- Le DPA prévoit la même exception à la suppression en fin de contrat : conservation lorsque c’est « necessary to combat harmful use of the Services » (H.1 b).
- La rétention zéro (ZDR) n’est pas un réglage universel : elle est limitée aux API éligibles, aux produits utilisant une clé API d’organisation et à Claude Code Enterprise ; sous ZDR, les résultats des classifieurs de sécurité restent conservés ; les modèles « couverts » sont gardés 30 jours sur toutes les plateformes, ZDR compris (V38).
- Conséquence pour le kit : la pseudonymisation avant l’envoi (contrôles C04 et C05) limite ce que ces rétentions contiennent, sans les supprimer.

## Avenant à négocier

Pour un service qui soutient une fonction critique ou importante, les écarts ci-dessus appellent un avenant DORA : lieux de traitement et préavis, niveaux de service chiffrés, assistance aux incidents TIC, coopération avec l’autorité, droits d’audit, participation aux TLPT, période de transition en sortie. Le paragraphe 4 de l’article 30 invite à considérer les clauses types élaborées par les autorités publiques.
