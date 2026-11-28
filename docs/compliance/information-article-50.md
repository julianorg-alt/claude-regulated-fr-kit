# Information des personnes au titre de l’article 50 du règlement IA

> **English summary.** Proposed notice for an organisation that gives staff or customers an assistant built on Claude behind the kit's gateway, under article 50 of the EU AI Act. Bracketed parts are to be replaced; the text must be reviewed by a lawyer or the data protection officer before use.

Backlog E9.5. Texte proposé à l’organisation qui met à disposition de son personnel ou de ses clients un assistant fondé sur Claude, derrière la passerelle du kit. Les crochets sont à remplacer. Le texte est à relire par le juriste ou le délégué à la protection des données avant diffusion.

## 1. Ce que demande l’article 50

Lu sur le texte publié au Journal officiel (V57), l’article 50 s’applique depuis le 2 août 2026 ; le règlement (UE) 2026/1744 n’a pas reporté le chapitre IV, et seul le marquage du paragraphe 2 bénéficie d’un délai jusqu’au 2 décembre 2026 pour les systèmes déjà sur le marché avant le 2 août 2026 (V56).

- Paragraphe 1 : le fournisseur d’un système d’IA destiné à interagir directement avec des personnes physiques le conçoit de sorte qu’elles soient informées qu’elles interagissent avec un système d’IA, sauf si cela ressort clairement du point de vue d’une personne normalement informée et raisonnablement attentive et avisée.
- Paragraphe 2 : le fournisseur d’un système qui génère des contenus de synthèse (audio, image, vidéo, texte) marque les sorties dans un format lisible par machine, sauf fonction d’assistance pour la mise en forme standard ou absence de modification substantielle des données fournies.
- Paragraphe 4 : le déployeur qui publie un texte généré ou manipulé par une IA dans le but d’informer le public sur des questions d’intérêt public l’indique, sauf si le texte a fait l’objet d’un examen humain ou d’un contrôle éditorial et qu’une personne assume la responsabilité éditoriale de la publication.
- Paragraphe 5 : l’information est donnée de manière claire et reconnaissable au plus tard lors de la première interaction ou de la première exposition, et respecte les exigences d’accessibilité.

Une organisation qui construit son propre assistant sur Claude et le met en service sous son nom est fournisseur de ce système au sens de l’article 3, point 3 ; voir `docs/compliance/roles-rgpd-ria.md`.

## 2. Texte court, affiché à l’ouverture de l’assistant

> Vous échangez avec [nom de l’assistant], un assistant d’intelligence artificielle. Ses réponses sont produites automatiquement par un modèle de langage (Claude, d’Anthropic, hébergé par Amazon Web Services dans l’Union européenne). Elles peuvent contenir des erreurs : vérifiez-les avant de les utiliser. Ne saisissez pas de données de santé ni de données dont vous n’avez pas besoin. [Lien vers l’information complète]

Le texte reste visible pendant l’échange (bandeau ou mention sous la zone de saisie) et lisible par un lecteur d’écran.

## 3. Information complète

> Qui vous répond : [Nom de l’assistant] est un système d’intelligence artificielle mis à disposition par [organisation]. Aucune personne ne lit vos messages en temps réel.
>
> Comment vos messages sont traités : Avant d’être transmis au modèle, vos messages passent par une passerelle de [organisation] qui remplace les données personnelles détectées (noms, numéros de sécurité sociale, IBAN, coordonnées) par des pseudonymes. Le modèle Claude est exécuté par Amazon Bedrock dans des régions de l’Union européenne. Les réponses sont réidentifiées par la passerelle avant de vous être affichées.
>
> Ce qui est conservé : La passerelle garde un journal d’audit sans le contenu de vos messages pendant [durée, de 6 mois à 3 ans]. [Si le journal de contenu est activé : un journal pseudonymisé est conservé [n] jours pour la qualité du service.]
>
> Limites : Les réponses peuvent être inexactes ou incomplètes. Elles ne constituent ni un conseil juridique, ni un avis médical, ni une décision de [organisation] à votre égard. [Si l’assistant peut agir : toute action irréversible proposée par l’assistant, comme un envoi ou un paiement, n’est exécutée qu’après la validation d’une personne habilitée.]
>
> Vos droits : Pour exercer vos droits sur vos données personnelles, contactez [délégué à la protection des données, adresse]. Responsable du traitement : [organisation].

## 4. Textes publiés pour informer le public

Lorsqu’un communiqué, une note d’information ou une page publique est rédigé avec l’assistant et publié pour informer le public sur une question d’intérêt public, ajouter la mention suivante, sauf relecture humaine et responsabilité éditoriale assumée par une personne nommée :

> Ce texte a été rédigé avec l’aide d’un système d’intelligence artificielle.

## 5. Ce que le kit fait et ne fait pas

- Le kit ne fournit pas d’interface de discussion : l’affichage du texte court relève du client (Claude Code, application interne).
- Le marquage lisible par machine du paragraphe 2 n’est pas fait par la passerelle. Savoir s’il incombe à l’organisation, au regard de l’exception de mise en forme standard, et ce que fait le fournisseur du modèle, reste à établir.
- Les éléments factuels du texte complet correspondent aux contrôles du kit : C01 (régions de l’UE), C04 (pseudonymisation), C10 et C12 (journaux), C17 (validation humaine des actions irréversibles). Retirer une phrase si le contrôle correspondant n’est pas déployé.
