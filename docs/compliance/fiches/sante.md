# Fiche sectorielle : santé

Backlog E9.4. Cette fiche s’adresse à un établissement ou un service sanitaire, social ou médico-social qui envisage Claude par Amazon Bedrock derrière la passerelle du kit. Elle dit ce que le kit couvre, ce qu’il ne couvre pas et ce qui n’a pas été vérifié.

## 1. Textes et autorités

- Hébergement des données de santé : article L. 1111-8 du code de la santé publique et certification HDS, dont l’Agence du numérique en santé (ANS) publie le référentiel (V61). La certification porte sur six activités : sites physiques, infrastructure matérielle, plateforme d’hébergement d’applications (activités 3 et 4), administration et exploitation du système d’information qui contient les données de santé, sauvegarde. Un hébergeur doit être certifié sur toutes les activités d’hébergement qu’il peut fournir à ses clients. L’ANS annonce la version 2.1 du référentiel pour octobre 2026.
- Usage de l’IA générative : « Premières clefs d’usage de l’IA générative en santé » de la Haute Autorité de santé, validé en octobre 2025 (V60). Le guide pose les lignes directrices A.V.E.C. : Apprendre (s’approprier le fonctionnement de l’outil), Vérifier (pertinence de l’usage, qualité de la requête, contrôle du contenu produit), Estimer (analyser dans le temps la qualité et l’adéquation de l’outil), Communiquer (échanger avec son écosystème pour améliorer les pratiques).
- RGPD : les données concernant la santé sont une catégorie particulière dont le traitement est interdit sauf exception (article 9) ; l’AIPD est requise notamment pour un traitement à grande échelle de ces données (article 35, paragraphe 3, point b) (V41, V62).
- Règlement IA : l’annexe III, point 5 a et d, vise l’éligibilité aux prestations, y compris les soins de santé, quand une autorité publique en décide, et le tri des patients aux urgences (V57). Ces usages sont à haut risque à partir du 2 décembre 2027 (V56).

## 2. Limite du kit : pas de certification HDS

Le kit ne revendique pas la certification HDS, et la chaîne qu’il décrit n’est pas qualifiée pour héberger des données de santé à caractère personnel :

- la certification HDS d’AWS, son périmètre et l’inclusion d’Amazon Bedrock dans ce périmètre n’ont pas été vérifiés ;
- la passerelle, le coffre de pseudonymes et la piste d’audit déployés par l’établissement sont eux-mêmes des briques d’hébergement ou d’exploitation au sens des activités 1 à 6 ; leur exploitant doit être certifié s’il héberge pour le compte d’un tiers.

Tant que ces points ne sont pas levés, le kit ne doit traiter que des contenus sans donnée de santé à caractère personnel : documents de procédure, textes réglementaires, synthèses déjà anonymisées. La pseudonymisation du kit (C04) réduit l’exposition ; elle ne transforme pas une donnée de santé en donnée anonyme, et le coffre de correspondances (C06) garde le lien avec la personne.

## 3. Ce que le kit couvre

| Clef A.V.E.C. ou attente | Contrôle du kit | Texte |
|---|---|---|
| Vérifier : contrôle du contenu produit avant usage | C14 (évaluation en français, correcteurs puis juge puis humain) ; C17 pour les actions d’agents | HAS-AVEC-2025, AI-ACT-14 |
| Estimer : qualité suivie dans le temps et à chaque changement de modèle | C14, C18 | HAS-AVEC-2025, AI-ACT-15 |
| Communiquer : traces partagées et vérifiables | C10, C13 | HAS-AVEC-2025, AI-ACT-12 |
| Minimisation et sécurité des données personnelles | C04, C05, C06, C12 | RGPD-25, RGPD-32 |
| Traitement dans l’UE | C01, C09 | RGPD-44 |

La clef « Apprendre » relève de la formation des professionnels ; le kit ne la couvre pas. Le règlement IA impose aussi de favoriser la maîtrise de l’IA par le personnel (article 4, réécrit par le règlement 2026/1744, V56).

## 4. Ce qui reste à la charge de l’établissement

- Vérifier qu’aucune donnée de santé à caractère personnel n’entre dans la passerelle tant que la chaîne n’est pas certifiée HDS, ou faire certifier la chaîne et contractualiser avec des hébergeurs certifiés.
- Rédiger l’AIPD et, pour un usage de l’annexe III, la FRIA.
- Former les professionnels (clef « Apprendre ») et diffuser l’information de l’article 50 (`docs/compliance/information-article-50.md`).
- Décider qui valide une réponse avant qu’elle n’entre dans un dossier patient.

## 5. Points ouverts

- Certification HDS d’AWS et inclusion d’Amazon Bedrock dans son périmètre : non vérifiées.
- Texte de l’article L. 1111-8 du code de la santé publique : Légifrance n’est pas lisible depuis la session (protection anti-robot) ; la fiche s’appuie sur la page de l’ANS.
- Contenu du référentiel HDS 2.1 annoncé pour octobre 2026 : non lu.
