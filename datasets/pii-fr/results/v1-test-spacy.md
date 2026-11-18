# Benchmark: spaCy fr_core_news_md (default)

100 documents. Hard negatives detected (wrong key, must be 0): 0.

## Strict match

Recall on identifiers with a key: 1.0

| Type | Gold | Precision | Recall | F1 |
|---|---|---|---|---|
| ADRESSE | 100 | 1.0 | 1.0 | 1.0 |
| CARTE | 25 | 1.0 | 1.0 | 1.0 |
| DATE_NAISSANCE | 100 | 1.0 | 1.0 | 1.0 |
| EMAIL | 75 | 1.0 | 1.0 | 1.0 |
| IBAN | 75 | 1.0 | 1.0 | 1.0 |
| NIR | 50 | 1.0 | 1.0 | 1.0 |
| ORGANISATION | 75 | 0.3931 | 0.9067 | 0.5484 |
| PERSONNE | 125 | 0.992 | 0.992 | 0.992 |
| SIREN | 25 | 1.0 | 1.0 | 1.0 |
| SIRET | 50 | 1.0 | 1.0 | 1.0 |
| TELEPHONE | 100 | 1.0 | 1.0 | 1.0 |

Recall by sector:

| Type | assurance | banque | public | sante |
|---|---|---|---|---|
| ADRESSE | 1.0 | 1.0 | 1.0 | 1.0 |
| CARTE | None | 1.0 | None | None |
| DATE_NAISSANCE | 1.0 | 1.0 | 1.0 | 1.0 |
| EMAIL | 1.0 | 1.0 | 1.0 | None |
| IBAN | 1.0 | 1.0 | 1.0 | None |
| NIR | None | None | 1.0 | 1.0 |
| ORGANISATION | 0.92 | 0.88 | 0.92 | None |
| PERSONNE | 1.0 | 1.0 | 1.0 | 0.98 |
| SIREN | None | 1.0 | None | None |
| SIRET | 1.0 | None | 1.0 | None |
| TELEPHONE | 1.0 | 1.0 | 1.0 | 1.0 |

## Overlap match

Recall on identifiers with a key: 1.0

| Type | Gold | Precision | Recall | F1 |
|---|---|---|---|---|
| ADRESSE | 100 | 1.0 | 1.0 | 1.0 |
| CARTE | 25 | 1.0 | 1.0 | 1.0 |
| DATE_NAISSANCE | 100 | 1.0 | 1.0 | 1.0 |
| EMAIL | 75 | 1.0 | 1.0 | 1.0 |
| IBAN | 75 | 1.0 | 1.0 | 1.0 |
| NIR | 50 | 1.0 | 1.0 | 1.0 |
| ORGANISATION | 75 | 0.4277 | 0.9867 | 0.5968 |
| PERSONNE | 125 | 0.992 | 0.992 | 0.992 |
| SIREN | 25 | 1.0 | 1.0 | 1.0 |
| SIRET | 50 | 1.0 | 1.0 | 1.0 |
| TELEPHONE | 100 | 1.0 | 1.0 | 1.0 |

Recall by sector:

| Type | assurance | banque | public | sante |
|---|---|---|---|---|
| ADRESSE | 1.0 | 1.0 | 1.0 | 1.0 |
| CARTE | None | 1.0 | None | None |
| DATE_NAISSANCE | 1.0 | 1.0 | 1.0 | 1.0 |
| EMAIL | 1.0 | 1.0 | 1.0 | None |
| IBAN | 1.0 | 1.0 | 1.0 | None |
| NIR | None | None | 1.0 | 1.0 |
| ORGANISATION | 0.96 | 1.0 | 1.0 | None |
| PERSONNE | 1.0 | 1.0 | 1.0 | 0.98 |
| SIREN | None | 1.0 | None | None |
| SIRET | 1.0 | None | 1.0 | None |
| TELEPHONE | 1.0 | 1.0 | 1.0 | 1.0 |

