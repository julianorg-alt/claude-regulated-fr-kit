# Modèle d’analyse d’impact des transferts

Analyse d’un transfert de données personnelles hors de l’EEE (RGPD, articles 44 et 46), en suivant les six étapes des recommandations 01/2020 du CEPD, version 2.0 du 18 juin 2021 (constat V43). Les passages remplis décrivent les flux que crée le kit ; les crochets sont à compléter par l’exportateur.

| Champ | Valeur |
|---|---|
| Exportateur | [Une banque régionale, par exemple] |
| Importateurs | [Liste, avec leur pays] |
| Version et date | [v1, JJ/MM/AAAA] |

## Étape 1 : connaître les transferts

Partir du registre des activités de traitement (RGPD, article 30, point e), qui doit déjà mentionner les transferts. Flux créés par le kit :

| Flux | Configuration du kit | Transfert hors EEE ? |
|---|---|---|
| Requêtes et réponses vers Amazon Bedrock | profil `eu.` appelé depuis une région de l’UE ; inventaire versionné, contrôle C01 | Non par le routage : les destinations sont des régions de l’UE (constat V5) |
| Même flux appelé depuis Londres ou Zurich | le profil `eu.` ajoute alors la région source à ses destinations (constat V5) | Oui : Royaume-Uni ou Suisse ; [vérifier la décision d’adéquation applicable] |
| API Anthropic directe (évaluations `make eval-live` uniquement) | `inference_geo` vaut `global` ou `us`, aucune valeur UE (constat V13) | Oui : à réserver aux tâches synthétiques, jamais à des données réelles |
| Journal d’audit, télémétrie | sans contenu (C10, C13), stockés dans le compte de l’exportateur | [selon la région du compte et du SIEM] |
| Accès du prestataire pour support ou détection d’abus | le constat V4 signale un stockage possible pour la détection d’abus dans les régions de destination | [à qualifier à partir du contrat AWS] |

Même quand les données restent dans l’UE, l’accès éventuel d’autorités d’un pays tiers au prestataire relève de l’étape 3 : [à analyser avec le service juridique].

## Étape 2 : instrument de transfert

Pour chaque flux marqué « oui » : décision d’adéquation (article 45) ou, à défaut, garantie appropriée de l’article 46, par exemple les clauses types de la Commission (article 46, paragraphe 2, point c).

| Flux | Instrument | Référence du document |
|---|---|---|
| [ ] | [décision d’adéquation, clauses types, autre] | [ ] |

## Étape 3 : efficacité de l’instrument au regard du droit du pays tiers

[Évaluer si la législation ou les pratiques du pays tiers applicables au transfert peuvent compromettre l’efficacité de l’instrument : accès des autorités publiques, voies de recours. Citer les sources consultées et leur date. Le kit ne fournit pas cette analyse.]

## Étape 4 : mesures supplémentaires

Mesures techniques fournies par le kit, à rapprocher des cas d’usage de l’annexe 2 des recommandations :

- Pseudonymisation avant l’envoi (C04, C05), correspondances gardées dans un coffre chiffré chez l’exportateur, isolé par appelant et expiré (C06). C’est la logique du cas n° 2 (données pseudonymisées), qui exige notamment que les informations supplémentaires restent sous le contrôle exclusif de l’exportateur dans l’EEE et qu’une analyse approfondie établisse que les données transmises ne peuvent pas être attribuées à une personne.
- Limite à reprendre telle quelle : la détection des données personnelles dans un texte libre n’est pas exhaustive (voir `datasets/README.md`) et le contexte d’un document peut suffire à désigner une personne. Le cas n° 2 n’est donc pas acquis pour tout texte. Lorsque le prestataire doit traiter les données en clair, la situation se rapproche du cas n° 6, pour lequel le CEPD, si le droit du pays tiers donne aux autorités un accès au-delà du nécessaire et proportionné, « n’est alors pas en mesure d’envisager une mesure technique efficace ».
- Chiffrement en transit et au repos : selon le paragraphe 95 des recommandations, il ne suffit pas si l’importateur détient les clés.
- Mesures contractuelles et organisationnelles : [à compléter].

## Étape 5 : étapes procédurales

[Formalités liées à l’instrument choisi : signature des clauses, modifications éventuelles, consultation de l’autorité de contrôle si l’instrument l’exige.]

## Étape 6 : réévaluation

[Fréquence de revue ; déclencheurs : changement de région ou de profil d’inférence (l’alerte de dérive de l’inventaire, `make inventory`, en est un), changement de prestataire ou de modèle, évolution du droit du pays tiers.]

| Revue | Qui | Date | Conclusion |
|---|---|---|---|
| [ ] | [fonction] | [ ] | [ ] |
