# Modèle d’entrées du registre d’informations DORA

Règlement (UE) 2022/2554 (DORA), article 28, paragraphe 3 : l’entité financière tient un registre d’informations sur tous les accords contractuels portant sur des services TIC fournis par des prestataires tiers, en distinguant ceux qui soutiennent des fonctions critiques ou importantes (constat V44). Les modèles types sont fixés par le règlement d’exécution (UE) 2024/2956 (constat V46).

Ce fichier ne remplace pas ces modèles. Il prépare, pour les deux accords que crée un déploiement du kit, les valeurs à reporter dans les modèles officiels, avec le modèle de destination entre parenthèses. Les codes de colonnes et les listes fermées sont ceux de l’annexe I du règlement d’exécution ; les prestataires personnes morales s’identifient par leur LEI ou leur EUID (article 3, paragraphe 5).

## Entrée : fournisseur du modèle

| Information (modèle) | Valeur |
|---|---|
| Entité financière qui tient le registre (B_01.01) | [Une banque régionale, par exemple] |
| Accord contractuel et numéro de référence (B_02.01, B_02.02) | [Accord client AWS, référence interne] |
| Prestataire direct (B_05.01) | Amazon Web Services [entité contractante et LEI, à reprendre du contrat] |
| Sous-traitant dans la chaîne (B_05.02) | Anthropic, fournisseur du modèle par l’intermédiaire de Bedrock [rang et LEI à confirmer dans les conditions AWS] |
| Service TIC (B_02.02) | Inférence de modèles de langage (Amazon Bedrock), accès par profil d’inférence `eu.` |
| Fonction soutenue (B_06.01) | [Fonction métier ; critique ou importante, ou non] |
| Pays de prestation et de traitement des données (B_02.02) | Régions UE de l’inventaire versionné (`infra/inventory/bedrock-claude.json`), vérifiées par le contrôle C01 ; destinations du profil `eu.` selon la région source (constat V5) |
| Lieu de stockage des données (B_02.02) | Selon les conditions Bedrock ; le constat V4 signale un stockage possible pour la détection d’abus dans les régions de destination |
| Données personnelles (B_02.02) | Oui, pseudonymisées par la passerelle (C04, C05) ; voir l’analyse d’impact des transferts |
| Évaluation du service (B_07.01, si fonction critique ou importante) | Substituabilité : second fournisseur par la route de sortie (C21) ; plan de sortie : `docs/compliance/plan-de-sortie.md` |
| Dates, durée, préavis (B_02.02) | [Contrat] |

## Entrée : passerelle et pseudonymisation

La passerelle du kit est exploitée par l’entité elle-même ou par son infogérant. Si un prestataire l’exploite, c’est un accord TIC distinct à inscrire au registre.

| Information (modèle) | Valeur |
|---|---|
| Prestataire (B_05.01) | [L’entité elle-même ou l’infogérant] |
| Service TIC (B_02.02) | Passerelle LLM : authentification, quotas, politique de requêtes, pseudonymisation, journal d’audit (contrôles C02 à C13) |
| Hébergement (B_02.02) | [Compte AWS de l’entité, région ; ou autre] |
| Composants tiers | Envoy AI Gateway, Open Policy Agent, Keycloak ou fournisseur d’identité de l’entité ; versions épinglées (C15) |
| Fonction soutenue (B_06.01) | [Mêmes fonctions que l’entrée précédente] |
| Journalisation et preuve | Audit sans contenu sous Object Lock (C10), CloudTrail (C11), télémétrie vers le SIEM (C13) |
| Coupure | Coupure d’urgence à trois niveaux (C08) |

## Points à vérifier avant usage

- Reporter chaque valeur dans le modèle officiel de l’annexe I du règlement d’exécution, avec ses listes fermées.
- Confirmer dans les conditions AWS la place d’Anthropic dans la chaîne de sous-traitance de Bedrock et son identifiant.
- Qualifier chaque fonction soutenue : critique ou importante, ou non. Si elle l’est, l’article 28, paragraphe 3, impose d’informer l’autorité compétente en temps utile du projet d’accord.
- Vérifier les clauses du contrat au regard de l’article 30 : voir la grille d’écarts `../grille-dpa-dora.md`.
