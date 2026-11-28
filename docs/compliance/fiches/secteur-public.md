# Fiche sectorielle : secteur public

> **English summary.** Sector sheet for State administrations, their operators and public interest groups considering Claude through Amazon Bedrock behind the kit's gateway. It states what the kit covers, what is out of scope and what has not been verified (SREN law article 31, SecNumCloud). It does not replace the advice of the information security officer or the data protection officer.

Backlog E9.4. Cette fiche s’adresse à une administration de l’État, à l’un de ses opérateurs ou à un groupement d’intérêt public qui envisage Claude par Amazon Bedrock derrière la passerelle du kit. Elle dit ce que le kit couvre, ce qu’il laisse hors de son périmètre et ce qui n’a pas été vérifié. Elle ne remplace ni l’avis du responsable de la sécurité des systèmes d’information ni celui du délégué à la protection des données.

## 1. Textes et autorités

- Article 31 de la loi n° 2024-449 du 21 mai 2024 visant à sécuriser et réguler l’espace numérique (loi SREN), lu sur le texte publié au Journal officiel (V64). Il s’applique aux administrations de l’État, à leurs opérateurs dont la liste est annexée au projet de loi de finances, et aux groupements d’intérêt public qui les comprennent, quand ils recourent à un service d’informatique en nuage fourni par un prestataire privé (paragraphe I).
- Qualification SecNumCloud de l’ANSSI : critères techniques et juridiques qui visent notamment une immunité aux lois extra-européennes, et qui ne préjugent pas du niveau de sécurité du service que le client héberge sur l’offre qualifiée (V63).
- Règlement IA : l’article 27 impose, avant le premier usage d’un système à haut risque de l’annexe III, une analyse d’impact sur les droits fondamentaux aux déployeurs qui sont des organismes de droit public (V42). Les usages de l’annexe III, point 5 a, qui vise l’éligibilité aux prestations et services publics essentiels, sont à haut risque à partir du 2 décembre 2027 (V56, V57).
- RGPD et règlement IA pour le reste : voir la matrice des rôles (`docs/compliance/roles-rgpd-ria.md`).

## 2. Hors périmètre : données d’une sensibilité particulière

L’article 31 distingue les données d’une sensibilité particulière (paragraphe II, V64) :

- les données qui relèvent de secrets protégés par la loi, notamment au titre des articles L. 311-5 et L. 311-6 du code des relations entre le public et l’administration ;
- les données nécessaires à l’accomplissement des missions essentielles de l’État, notamment la sauvegarde de la sécurité nationale, le maintien de l’ordre public et la protection de la santé et de la vie des personnes.

Quand un système traite de telles données, que ce soit des données personnelles ou non, et que leur violation est susceptible d’atteindre l’ordre public, la sécurité publique, la santé ou la vie des personnes ou la propriété intellectuelle, l’administration doit veiller à ce que le service en nuage protège ces données contre tout accès non autorisé par le droit de l’Union ou d’un État membre émanant d’autorités publiques d’États tiers (paragraphe I, V64).

Le kit ne répond pas à cette exigence et ne prétend pas y répondre :

- il s’appuie sur Amazon Bedrock, fourni par un prestataire dont le siège est hors de l’Union ; la qualification SecNumCloud d’AWS, ou l’absence d’une telle qualification pour Bedrock, n’a pas été vérifiée ;
- la pseudonymisation (C04) et le chiffrement du coffre (C06) réduisent l’exposition de données personnelles ; ils ne protègent ni un secret protégé par la loi ni une donnée de mission essentielle, qui restent lisibles par le modèle une fois la requête envoyée ;
- la région de traitement dans l’Union (C01, C09) répond à une question de localisation, pas à celle de l’accès par des autorités d’États tiers.

Les contenus de sensibilité particulière ne doivent donc pas entrer dans la passerelle. Le kit convient à des contenus sans cette sensibilité : textes publics, documents de procédure, aide à la rédaction, à condition que l’administration ait fait ce classement.

## 3. Ce que le kit couvre

| Attente | Contrôle du kit | Texte |
|---|---|---|
| Traitement dans l’Union et sortie réseau limitée | C01, C09 | RGPD-44 |
| Minimisation et sécurité des données personnelles | C04, C05, C06, C12 | RGPD-25, RGPD-32 |
| Traces conservées et vérifiables pour l’analyse d’impact et le contrôle | C10, C11, C13 | AI-ACT-12 |
| Contrôle humain et qualité des réponses | C14, C17, C20 | AI-ACT-14, AI-ACT-15 |
| Coupure d’urgence et plafonds d’usage | C07, C08 | AI-ACT-14 |

## 4. Ce qui reste à la charge de l’administration

- Classer chaque usage : sensibilité particulière au sens du paragraphe II ou non, et haut risque au sens de l’annexe III ou non.
- Pour un usage qui traite des données de sensibilité particulière, choisir un service qui répond au paragraphe I, ce que le kit ne fournit pas.
- Rédiger l’AIPD et, pour un usage de l’annexe III, la FRIA de l’article 27 à partir des modèles du dossier.
- Informer les agents et les usagers (`docs/compliance/information-article-50.md`).
- Vérifier le décret d’application prévu au paragraphe V, qui précise les critères de sécurité et de protection, y compris la détention du capital.

## 5. Points ouverts

- Décret en Conseil d’État du paragraphe V : publication, contenu et critères de détention du capital non lus.
- Modifications postérieures de l’article 31 : la version lue est celle du Journal officiel ; les versions ultérieures n’ont pas été consultées.
- Qualification SecNumCloud d’AWS et inclusion de Bedrock : non vérifiées. La page de l’ANSSI ne donne pas de numéro de version du référentiel (V63).
- Doctrine d’emploi du nuage par l’État (circulaire de la Première ministre sur le nuage au centre, liste des opérateurs annexée au projet de loi de finances) : non lue.
