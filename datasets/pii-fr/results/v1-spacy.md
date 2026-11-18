# Benchmark: spaCy fr_core_news_md (default)

200 documents. Hard negatives detected (wrong key, must be 0): 0.

## Strict match

Recall on identifiers with a key: 1.0

| Type | Gold | Precision | Recall | F1 |
|---|---|---|---|---|
| ADRESSE | 200 | 1.0 | 1.0 | 1.0 |
| CARTE | 50 | 1.0 | 1.0 | 1.0 |
| DATE_NAISSANCE | 200 | 1.0 | 1.0 | 1.0 |
| EMAIL | 150 | 1.0 | 1.0 | 1.0 |
| IBAN | 150 | 1.0 | 1.0 | 1.0 |
| NIR | 100 | 1.0 | 1.0 | 1.0 |
| ORGANISATION | 150 | 0.39 | 0.8867 | 0.5418 |
| PERSONNE | 250 | 0.988 | 0.988 | 0.988 |
| SIREN | 50 | 1.0 | 1.0 | 1.0 |
| SIRET | 100 | 1.0 | 1.0 | 1.0 |
| TELEPHONE | 200 | 1.0 | 1.0 | 1.0 |

Recall by sector:

| Type | assurance | banque | public | sante |
|---|---|---|---|---|
| ADRESSE | 1.0 | 1.0 | 1.0 | 1.0 |
| CARTE | None | 1.0 | None | None |
| DATE_NAISSANCE | 1.0 | 1.0 | 1.0 | 1.0 |
| EMAIL | 1.0 | 1.0 | 1.0 | None |
| IBAN | 1.0 | 1.0 | 1.0 | None |
| NIR | None | None | 1.0 | 1.0 |
| ORGANISATION | 0.9 | 0.86 | 0.9 | None |
| PERSONNE | 1.0 | 1.0 | 0.98 | 0.98 |
| SIREN | None | 1.0 | None | None |
| SIRET | 1.0 | None | 1.0 | None |
| TELEPHONE | 1.0 | 1.0 | 1.0 | 1.0 |

## Overlap match

Recall on identifiers with a key: 1.0

| Type | Gold | Precision | Recall | F1 |
|---|---|---|---|---|
| ADRESSE | 200 | 1.0 | 1.0 | 1.0 |
| CARTE | 50 | 1.0 | 1.0 | 1.0 |
| DATE_NAISSANCE | 200 | 1.0 | 1.0 | 1.0 |
| EMAIL | 150 | 1.0 | 1.0 | 1.0 |
| IBAN | 150 | 1.0 | 1.0 | 1.0 |
| NIR | 100 | 1.0 | 1.0 | 1.0 |
| ORGANISATION | 150 | 0.4311 | 0.98 | 0.5988 |
| PERSONNE | 250 | 0.988 | 0.988 | 0.988 |
| SIREN | 50 | 1.0 | 1.0 | 1.0 |
| SIRET | 100 | 1.0 | 1.0 | 1.0 |
| TELEPHONE | 200 | 1.0 | 1.0 | 1.0 |

Recall by sector:

| Type | assurance | banque | public | sante |
|---|---|---|---|---|
| ADRESSE | 1.0 | 1.0 | 1.0 | 1.0 |
| CARTE | None | 1.0 | None | None |
| DATE_NAISSANCE | 1.0 | 1.0 | 1.0 | 1.0 |
| EMAIL | 1.0 | 1.0 | 1.0 | None |
| IBAN | 1.0 | 1.0 | 1.0 | None |
| NIR | None | None | 1.0 | 1.0 |
| ORGANISATION | 0.94 | 1.0 | 1.0 | None |
| PERSONNE | 1.0 | 1.0 | 0.98 | 0.98 |
| SIREN | None | 1.0 | None | None |
| SIRET | 1.0 | None | 1.0 | None |
| TELEPHONE | 1.0 | 1.0 | 1.0 | 1.0 |

