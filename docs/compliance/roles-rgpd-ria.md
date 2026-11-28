# Matrice des rôles : RGPD et règlement IA

> **English summary.** Role matrix: for each actor in a typical deployment of the kit, the probable role under the GDPR (controller, processor) and under the EU AI Act (provider, deployer). A starting point for the record of processing, the DPIA and the contract; the real role depends on the facts and is decided case by case.

Backlog E9.5. La matrice indique, pour chaque acteur d’un déploiement type du kit, son rôle probable au sens du RGPD et du règlement IA. Elle sert de point de départ au registre des traitements, à l’AIPD et au contrat ; le rôle réel dépend des faits et se décide au cas par cas.

## 1. Définitions retenues

- RGPD, article 4 (V62) : le responsable du traitement « détermine les finalités et les moyens du traitement », seul ou conjointement ; le sous-traitant « traite des données à caractère personnel pour le compte du responsable du traitement ». Article 28 : le responsable ne fait appel qu’à des sous-traitants présentant des garanties suffisantes, et un sous-traitant qui détermine les finalités et les moyens en violation du règlement est considéré comme responsable pour ce traitement.
- Règlement IA, article 3 (V57) : le fournisseur développe ou fait développer un système d’IA ou un modèle d’IA à usage général et le met sur le marché ou le met en service sous son propre nom ou sa propre marque ; le déployeur utilise un système d’IA sous sa propre autorité, hors activité personnelle non professionnelle.
- Règlement IA, article 25, paragraphe 1 (V57) : un déployeur ou un tiers devient fournisseur d’un système à haut risque s’il le commercialise sous son nom, s’il lui apporte une modification substantielle, ou s’il modifie la destination d’un système, y compris d’un système d’IA à usage général, de sorte qu’il devient à haut risque.

## 2. Matrice

| Acteur | RGPD | Règlement IA | Fondement et réserve |
|---|---|---|---|
| L’organisation qui déploie le kit (une banque régionale, un assureur, un hôpital, une administration) | Responsable du traitement | Déployeur de l’assistant ; fournisseur du système d’IA qu’elle construit sur Claude et met en service sous son nom | Elle fixe les finalités (assistance, rédaction, agents) et les moyens (passerelle, régions, durées). Si l’usage relève de l’annexe III, l’article 25 peut faire d’elle le fournisseur du système à haut risque. |
| Amazon Web Services (Bedrock) | Sous-traitant | Ni fournisseur ni déployeur du système de l’organisation ; distributeur ou fournisseur d’accès au modèle, à qualifier | Traite les requêtes pour le compte de l’organisation. Le contrat AWS et son avenant de traitement n’ont pas été lus (point ouvert de la grille E9.3). |
| Anthropic | Sous-traitant ultérieur d’AWS pour Bedrock, à confirmer ; sous-traitant direct pour l’API Anthropic (DPA, V45) | Fournisseur du modèle d’IA à usage général Claude | Les obligations des fournisseurs de modèles à usage général (chapitre V) lui incombent. Sur Bedrock, sa place dans la chaîne de sous-traitance dépend du contrat AWS, non lu. |
| Éditeur de l’outil client (Claude Code, application interne) | Sous-traitant si l’outil traite des données pour l’organisation ; hors champ s’il s’exécute en local sans envoi | Composant du système de l’organisation | À examiner outil par outil. |
| Serveurs MCP internes | Moyens de l’organisation | Composants du système | Inscrits au registre `agents/registry/servers.toml` (C19). |
| Serveurs MCP d’un tiers | Sous-traitant ou destinataire selon le service | Composant fourni par un tiers | Un serveur hors registre est refusé par le proxy (C19). |
| Personnel utilisateur | Personnes agissant sous l’autorité du responsable (article 29) | Personnes à qui le déployeur assure la maîtrise de l’IA (article 4) | Formation et consignes d’usage. |
| Clients, patients, administrés cités dans les requêtes | Personnes concernées | Personnes concernées ou exposées ; information des articles 26, paragraphe 11, et 50 | Information : `docs/compliance/information-article-50.md`. |
| Mainteneurs du kit (ce dépôt) | Hors champ : ils ne traitent aucune donnée | Hors champ : ils ne mettent pas le système sur le marché | Le kit est un ensemble de configurations et de tests sous licence Apache 2.0 ; il n’est pas un service. |

## 3. Conséquences pour le dossier

- Registre des traitements (RGPD, article 30) : l’organisation y inscrit l’assistant avec AWS comme sous-traitant et les régions de l’Union retenues (C01).
- AIPD (`docs/compliance/modeles/aipd.md`) et, pour un usage à haut risque visé par l’article 27, FRIA (`docs/compliance/modeles/fria.md`).
- Contrat : clauses de l’article 28 du RGPD et, pour une entité financière, de l’article 30 de DORA (`docs/compliance/grille-dpa-dora.md`).
- Si l’organisation est fournisseur d’un système à haut risque : obligations du chapitre III, section 2, à partir du 2 décembre 2027 pour l’annexe III (V56), que le kit ne couvre que pour les journaux (C10), le contrôle humain (C17) et la robustesse (C14, C18).

## 4. Points ouverts

- Qualification d’AWS au sens du règlement IA (distributeur, ou autre) : non tranchée, aucune source lue sur ce point.
- Place d’Anthropic dans la chaîne de sous-traitance sur Bedrock : dépend du contrat AWS, non lu.
