# French PII data set and benchmark

`pii-fr/` holds a synthetic data set of French documents with personal data, and the benchmark of the kit's detectors on it (backlog E4). Licence: CC BY 4.0 (decision K5, `pii-fr/LICENSE`).

## Content

| File | Documents | Seed | Use |
|---|---|---|---|
| `pii-fr/v1.jsonl` | 200, 50 per sector | 2026 | development: the detectors were tuned on it |
| `pii-fr/v1-test.jsonl` | 100, 25 per sector | 7 | check: same templates, other random values |
| `pii-fr/results/*.md`, `*.json` | | | benchmark results, regenerated and checked by CI |

Four sectors in equal parts (decision K4): a bank complaint letter, an insurance claim, a medical consultation report and a housing-aid request to a public body. Each document is fiction: names from short lists of common French given names and surnames, invented organisations and streets, e-mail addresses on `example.org`, identifiers with a valid key. Any match with a real person, company or account is chance, except where the values below are reserved. Each document also carries a hard negative: an identifier of the same shape with a wrong key, which no detector may report.

One JSON object per line, character offsets, labels equal to the pseudonym types:

```json
{"id": "banque-0001", "sector": "banque", "template": "reclamation", "text": "...",
 "spans": [{"start": 71, "end": 84, "label": "PERSONNE"}],
 "negatives": [{"start": 498, "end": 531, "kind": "IBAN"}]}
```

## Reserved values

Before publication (owner decision of 2026-11-17) the generator stopped using random values in real formats. Sources and read dates are in `docs/sources/verifications.md` (V68 to V73).

| Type | Construction | Status |
|---|---|---|
| Telephone | Only the ARCEP numbers for audiovisual works: roots 01 99 00, 02 61 91, 03 53 01, 04 65 71, 05 36 49, 06 39 98 followed by four digits (V68) | verified |
| SIREN, SIRET | SIREN from `reserved-siren.json` (valid Luhn key, unknown to the public company search on 2026-11-17, V69); `verify_siren.py` rebuilds the list; SIRET built on those SIREN | verified, residual risk for non-disclosable units |
| Card | Nine published network test cards (V70) | verified against one acquirer's page |
| IBAN | Bank code `00000`, valid RIB key and IBAN key | **not verified** against an official bank list (V71) |
| NIR | Random, valid key | **open**: no reserved construction found (V72, searched again in V73) |

The tests fail if a generated telephone number, SIREN, SIRET or card number leaves these lists.

## Reproduce

```bash
python3 datasets/generate.py --seed 2026 --per-sector 50 --out datasets/pii-fr/v1.jsonl
python3 datasets/generate.py --seed 7 --per-sector 25 --out datasets/pii-fr/v1-test.jsonl
make benchmark          # writes pii-fr/results
make test-pseudo        # fails if the committed set or results are stale, or if recall on identifiers < 0.99
```

`make benchmark BACKEND=gliner` adds the optional GLiNER model (needs `crfr-pseudo[gliner]` and about 1.2 GB of weights); its results are not committed by CI.

## Results (default detector, spaCy `fr_core_news_md`)

Strict match (same type, same boundaries), development set: recall 1.0 on identifiers with a key (NIR, IBAN, card, SIREN, SIRET), 1.0 on telephone numbers, e-mail addresses, dates of birth and addresses, 0.99 on person names; organisations reach a recall of 0.89 with a precision of 0.39. No hard negative is detected. Full tables: [`pii-fr/results/v1-spacy.md`](pii-fr/results/v1-spacy.md) and [`pii-fr/results/v1-test-spacy.md`](pii-fr/results/v1-test-spacy.md).

Read these figures for what they are:

- The detectors were tuned on the development set, and the check set shares its templates. A score of 1.0 means the detectors handle these four layouts, not that they handle any French text. Real documents have other layouts, typos, OCR noise and names outside the lists. A held-out set written from other templates is still to do.
- The first run on the set found four bugs, fixed in the same change: a city name that ran onto the next line, model spans that swallowed a neighbouring identifier, card numbers found inside an IBAN with a wrong key, and a SIREN found inside a longer number.
- Organisation names are where the default model is weak. The policy does not depend on them: identifiers with a key are the hard criterion, and any that remain in clear text make the gateway refuse the request.
