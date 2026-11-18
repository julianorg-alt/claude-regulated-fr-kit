# Fiche sectorielle : banque et assurance

Backlog E9.4. Cette fiche s’adresse à un établissement de crédit, une entreprise d’assurance ou un intermédiaire soumis au contrôle de l’ACPR, qui déploie Claude par Amazon Bedrock derrière la passerelle du kit. Elle dit ce que le kit couvre, ce qui reste à la charge de l’établissement et ce qui n’a pas été vérifié. Elle ne remplace ni l’avis du responsable de la conformité ni celui du délégué à la protection des données.

## 1. Textes et autorités

- Règlement IA (UE) 2024/1689 (constats V42 et V57), modifié par le règlement (UE) 2026/1744, dit omnibus numérique sur l’IA (V56).
- DORA, règlement (UE) 2022/2554, articles 9, 28 et 30 (V44), et règlement d’exécution (UE) 2024/2956 sur le registre d’informations (V46).
- RGPD, articles 5, 25, 30, 32, 35, 44 et 46 (V41).
- Assurance : avis de l’EIOPA sur la gouvernance et la gestion des risques de l’IA, EIOPA-BoS-25-360 du 6 août 2025 (V59). L’avis s’adresse aux autorités nationales et ne crée pas d’exigence nouvelle ; il dit comment l’EIOPA lit Solvabilité II, la directive sur la distribution d’assurances et DORA pour l’IA.
- Autorité : l’ACPR est désignée autorité de surveillance du marché pour les systèmes d’IA à haut risque du secteur financier (V58). Elle peut aussi examiner les autres systèmes d’IA des organismes qu’elle contrôle, dans le cadre de sa supervision habituelle.

## 2. Haut risque au sens du règlement IA

Deux usages de l’annexe III, point 5, concernent directement le secteur (V57) :

- b) évaluer la solvabilité des personnes physiques ou établir leur note de crédit, à l’exception des systèmes utilisés pour détecter les fraudes financières ;
- c) évaluer les risques et fixer les tarifs des personnes physiques en assurance vie et en assurance maladie.

Depuis le règlement 2026/1744, les sections 1 à 3 du chapitre III s’appliquent à partir du 2 décembre 2027 pour les systèmes de l’annexe III, et du 2 août 2028 pour ceux de l’annexe I (V56). L’ACPR reprend la date du 2 décembre 2027 pour le secteur financier (V58). Le kit ne range pas un usage dans le haut risque à la place de l’établissement : un assistant de rédaction ou de recherche documentaire n’en relève pas, un outil qui propose une décision d’octroi de crédit fondée sur le modèle en relève.

Pour un usage à haut risque, l’établissement est déployeur (article 26) et, s’il intègre le modèle dans un système d’IA qu’il met en service sous son propre nom, il peut devenir fournisseur au sens de l’article 25 (voir `docs/compliance/roles-rgpd-ria.md`). L’article 26 prévoit deux aménagements pour les établissements financiers (V57) : le respect des règles de gouvernance de la législation financière vaut respect de l’obligation de surveillance du paragraphe 5, et les journaux sont tenus dans la documentation exigée par cette législation (paragraphe 6, durée d’au moins six mois sauf disposition contraire). L’analyse d’impact sur les droits fondamentaux (article 27) vise les déployeurs des points 5 b et c ; le modèle `docs/compliance/modeles/fria.md` la prépare, et elle peut renvoyer aux sections de l’AIPD qui couvrent déjà une obligation (article 27, paragraphe 4, réécrit par le règlement 2026/1744).

## 3. Ce que le kit couvre

| Attente | Contrôle du kit | Texte |
|---|---|---|
| Traitement dans l’UE, sans repli vers une région hors inventaire | C01, C09 | RGPD-44, AWS-BEDROCK-GEO |
| Données personnelles minimisées avant le fournisseur | C04, C05, C06 | RGPD-25, RGPD-32 |
| Journaux des événements et piste d’audit inaltérable, conservée au moins six mois | C10, C11, C13 | AI-ACT-12, AI-ACT-26, CNIL-2021-122 |
| Contrôle humain des actions d’agents à effet irréversible | C17, C20 | AI-ACT-14 |
| Exactitude et robustesse mesurées avant mise en service et à chaque changement de modèle | C14, C18 | AI-ACT-15 |
| Surveillance et protection des systèmes TIC, coupure d’urgence | C07, C08, C13 | DORA-9 |
| Registre d’informations et clauses contractuelles | modèle `registre-dora.md`, grille `grille-dpa-dora.md` | DORA-28, DORA-30, DORA-ITS-2024-2956 |
| Gouvernance des outils MCP et des agents | C19, C20 | OWASP-LLM-2025 |

Pour l’assurance, l’avis de l’EIOPA (V59) organise les attentes en sept thèmes : système de gestion des risques, équité et éthique, gouvernance des données, documentation et conservation des traces, transparence et explicabilité, contrôle humain, exactitude, robustesse et cybersécurité. Il demande une analyse d’impact par système, puis des mesures proportionnées à cet impact. Le kit fournit la matière technique de quatre thèmes (traces C10 à C13, contrôle humain C17 et C20, robustesse C14 et C18, cybersécurité C07 à C09) ; l’équité, l’explicabilité et la gouvernance des données d’entraînement relèvent de l’établissement et du fournisseur du modèle.

## 4. Ce qui reste à la charge de l’établissement

- Classer chaque usage (haut risque ou non) et tenir l’inventaire des systèmes d’IA.
- Rédiger l’AIPD et, pour les points 5 b et c, la FRIA, à partir des modèles du dossier.
- Informer les personnes : l’information de l’article 50 (texte proposé dans `docs/compliance/information-article-50.md`) et, pour un système à haut risque qui prend ou facilite une décision les concernant, celle de l’article 26, paragraphe 11.
- Informer les représentants du personnel avant d’utiliser un système à haut risque sur le lieu de travail (article 26, paragraphe 7).
- Obtenir du fournisseur les informations sur les caractéristiques, les données et les limites du modèle : l’avis de l’EIOPA rappelle que l’entreprise reste responsable des systèmes fournis par un tiers (paragraphe 3.11).
- Inscrire Bedrock au registre d’informations DORA et analyser le contrat AWS (non lu par le kit).
- Mesurer l’équité d’un usage de tarification ou de solvabilité : le kit n’a pas de métrique d’équité.

## 5. Points ouverts

- Conditions contractuelles d’AWS (accord client, avenant de traitement) : non lues ; la grille DORA ne couvre que le DPA d’Anthropic.
- Positions de l’ACPR propres à l’IA générative : la page lue (V58) renvoie à des réunions de Place dont les supports n’ont pas été lus.
- Lignes directrices de la Commission sur la classification des systèmes à haut risque : non lues.
