# Modèle d’AIPD : assistant IA derrière la passerelle du kit

> **English summary.** Template for a data protection impact assessment (GDPR article 35) of an AI assistant behind the kit's gateway. Filled passages describe what the kit sets up and point to controls in the traceability matrix; brackets are for the controller to complete. It does not say whether a DPIA is mandatory for your processing.

Analyse d’impact relative à la protection des données (RGPD, article 35). Le paragraphe 7 de l’article fixe un contenu minimal en quatre points, repris par les sections 1 à 4 (texte lu sur le site de la CNIL, constat V41). Les passages déjà remplis décrivent ce que le kit met en place et renvoient aux contrôles de la [matrice de traçabilité](../matrix.md) ; les crochets sont à compléter par le responsable du traitement.

Ce modèle ne dit pas si une AIPD est obligatoire pour votre traitement : c’est au responsable du traitement d’en juger, au regard de l’article 35, paragraphes 1 et 3, et de la liste publiée par la CNIL.

| Champ | Valeur |
|---|---|
| Organisme | [Une banque régionale, par exemple] |
| Responsable du traitement | [Nom de l’entité] |
| Délégué à la protection des données | [Fonction, pas de nom dans un modèle partagé] |
| Version et date | [v1, JJ/MM/AAAA] |
| Traitements couverts | [Assistant de rédaction pour les conseillers, résumé de courriers, etc.] |

## 1. Description du traitement et de ses finalités

Finalités : [lister chaque usage, par exemple résumer un courrier entrant, rédiger un projet de réponse relu par un conseiller]. Base légale et, le cas échéant, intérêt légitime poursuivi : [à compléter].

Opérations de traitement prévues par le kit :

1. L’utilisateur s’authentifie auprès du fournisseur d’identité ; la passerelle vérifie le jeton et le groupe (C02).
2. Le garde pseudonymise les données personnelles françaises détectées dans la requête (C04) et refuse la requête si un identifiant reste en clair (C05). Les correspondances restent dans un coffre chiffré, isolé par appelant et expiré (C06).
3. La requête pseudonymisée part vers Amazon Bedrock par un profil d’inférence `eu.` dont l’inventaire versionné ne contient que des régions de l’UE (C01, constats V1 et V5) ; la sortie réseau est limitée à ces points d’accès (C09). Aucune identité ni adresse IP du client n’est transmise (C03).
4. La réponse est réidentifiée par le garde avant d’être rendue à l’utilisateur (C04).
5. Le journal d’audit enregistre qui a appelé quoi, quand et avec quelle décision, sans contenu (C10, C11) ; un journal de contenu pseudonymisé de quelques jours est optionnel (C12).

Catégories de personnes concernées : [clients, prospects, agents, tiers cités dans les documents]. Catégories de données : [identité, coordonnées, données bancaires, etc.]. Données sensibles au sens de l’article 9 : [oui ou non ; si oui, lesquelles et pourquoi].

Destinataires : AWS en qualité de sous-traitant ; [autres]. Durées de conservation : audit de 6 mois à 3 ans selon la recommandation CNIL 2021-122 (C10, constat V32) ; contenu pseudonymisé de [1 à 30] jours si le journal de contenu est activé (C12) ; correspondances du coffre : [durée configurée].

## 2. Nécessité et proportionnalité

- Minimisation : seuls les extraits nécessaires à la tâche sont envoyés [à justifier par usage] ; les identifiants sont remplacés par des pseudonymes avant l’envoi (C04, C05).
- Limitation de la conservation : voir les durées de la section 1 ; aucun contenu en clair n’est journalisé (C10, C12).
- Exactitude : les usages sont évalués en français avant mise en service et à chaque changement de modèle (C14) ; [seuil d’acceptation retenu].
- Information des personnes et exercice des droits : [mentions d’information, procédure d’accès, de rectification et d’opposition].
- Sous-traitance et transferts : [contrat avec AWS, analyse des transferts : voir le modèle d’analyse d’impact des transferts].

## 3. Risques pour les droits et libertés des personnes

Pour chaque risque, estimer la gravité et la vraisemblance [échelle retenue], avant et après les mesures de la section 4.

| Risque | Source | Gravité | Vraisemblance | Mesures (section 4) |
|---|---|---|---|---|
| Accès illégitime aux données envoyées au modèle | fournisseur, autorité d’un pays tiers | [ ] | [ ] | C01, C04, C09 |
| Réidentification des pseudonymes | fuite du coffre ou des journaux | [ ] | [ ] | C06, C12 |
| Réponse inexacte reprise sans contrôle et décision défavorable | modèle, usage | [ ] | [ ] | C14, [relecture humaine] |
| Détection incomplète d’une donnée personnelle (nom rare, adresse) | limites de la détection | [ ] | [ ] | C04, C16, [consigne aux utilisateurs] |
| Usage détourné ou excessif | utilisateur interne | [ ] | [ ] | C02, C07, C08, C10 |
| Divulgation d’une donnée d’un tiers dans une réponse | contenu du document | [ ] | [ ] | C14 |

Risque résiduel connu, à reprendre tel quel : la détection des données personnelles n’est pas exhaustive. Le rappel mesuré sur le jeu de test du kit est de 1,0 pour les identifiants à clé de contrôle, mais la précision sur les organisations est de 0,40 et les détecteurs ont été réglés sur ces mêmes modèles de documents (voir `datasets/README.md`).

## 4. Mesures envisagées

| Mesure | Contrôle | Preuve automatisée |
|---|---|---|
| Inférence limitée à l’UE | C01 | matrice de traçabilité |
| Authentification et autorisation par groupe | C02 | matrice de traçabilité |
| Pseudonymisation et refus des identifiants en clair | C04, C05 | matrice de traçabilité |
| Coffre de correspondances chiffré et expiré | C06 | matrice de traçabilité |
| Quotas, budgets et coupure d’urgence | C07, C08 | matrice de traçabilité |
| Sortie réseau limitée | C09 | matrice de traçabilité |
| Traçabilité sans contenu, scellée | C10, C11, C13 | matrice de traçabilité |
| Évaluation avant mise en service | C14 | matrice de traçabilité |
| [Mesures organisationnelles : formation, charte, relecture humaine] | | [procédure interne] |

Tester régulièrement l’efficacité des mesures (RGPD, article 32, paragraphe 1, point d) : `make ci` et `make e2e` rejouent les tests cités par la matrice ; [fréquence de revue].

## 5. Avis et validation

| Étape | Qui | Date | Avis |
|---|---|---|---|
| Avis du délégué à la protection des données (article 35, paragraphe 2) | [fonction] | [ ] | [ ] |
| Avis des personnes concernées ou de leurs représentants, le cas échéant (paragraphe 9) | [ ] | [ ] | [ ] |
| Décision du responsable du traitement | [fonction] | [ ] | [ ] |
| Prochaine revue (paragraphe 11, en cas de changement du risque) | | [ ] | |

Lorsque l’analyse indique que le traitement présenterait un risque élevé si le responsable du traitement ne prenait pas de mesures pour l’atténuer, l’article 36 impose de consulter la CNIL avant le traitement.
