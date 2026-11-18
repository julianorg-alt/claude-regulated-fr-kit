# Pseudonymisation of French personal data

Package `crfr_pseudo` (backlog E3). The gateway's guard runs it on every request before anything reaches Bedrock, and restores the original values in the answer, buffered or streamed.

```
"Je suis Jean Martin, NIR 1 85 05 78 006 084 91"   ->  Bedrock reads  "Je suis <PERSONNE_1>, NIR <NIR_1>"
"Bien noté <PERSONNE_1>"                            <-  the client reads "Bien noté Jean Martin"
```

## What is detected

| Pseudonym | How | Check |
|---|---|---|
| `NIR` | pattern, spaces allowed, Corsica 2A and 2B | key = 97 − (number mod 97), INSEE |
| `IBAN` | pattern, any country | mod 97 = 1; French IBANs have 27 characters (ECBS) |
| `CARTE` | 15 to 19 digits | Luhn |
| `SIRET`, `SIREN` | 14 and 9 digits | Luhn (INSEE); La Poste rule for SIREN 356000000 |
| `NUMERO_FISCAL` | 13 digits after a context word ("numéro fiscal", "SPI") | none: no public check digit was found |
| `TELEPHONE` | French numbering, `0X` or `+33` | none |
| `EMAIL` | pattern | none |
| `DATE_NAISSANCE` | a date after "né", "née", "naissance" | none |
| `ADRESSE` | number, street type, name, optional postcode and city | none |
| `PERSONNE`, `ORGANISATION` | spaCy `fr_core_news_md` through Presidio | none |
| `IDENTIFIANT_PATIENT` | EDS-Pseudo only (IPP, NDA) | none |

A number whose key is wrong is not an identifier and stays as it is. Overlapping detections are resolved by length, then score, then the order of the table.

Optional backends (`backends.py`), off by default because they need PyTorch or gated weights:
- GLiNER `urchade/gliner_multi_pii-v1` (Apache-2.0, covers French), pinned to a revision: `pip install crfr-pseudo[gliner]`, then `Detector(extra=[GlinerBackend()])`.
- EDS-Pseudo (AP-HP, BSD-3-Clause) for clinical texts. Its public weights are gated on Hugging Face: request access, download them, then `EdsPseudoBackend(model_path=...)`.

Decision K10 named GLiNER as the main model with spaCy as a fallback. The kit ships spaCy by default instead: the GLiNER model weighs about 1.2 GB plus PyTorch, which would make the gateway image and every CI run several times heavier, and identifiers, the criterion of E3, do not depend on the model. The benchmark of E4 measures both.

## Vault

Pseudonyms are typed and numbered per session (`<PERSONNE_1>`, `<PERSONNE_2>`, `<NIR_1>`): the same value keeps the same pseudonym for the whole conversation. The client chooses the session with the `x-crfr-session` header; the guard scopes it to the application and the user, so one user cannot open another user's mapping. Without the header, the session is the request.

Originals are encrypted with AES-256-GCM; the lookup index is an HMAC of the normalised value. Entries expire after `ttl_s` (one hour by default, extended on use) and are then deleted. The key comes from `CRFR_VAULT_KEY` (32 bytes, base64) injected at start-up; without it the guard uses a random in-memory key and every mapping is lost on restart, which is what the local demo does. The vault is never written to the decision log, which only records counts per type.

## Streaming

In a streamed answer a pseudonym can be split across two deltas (`<PERS` then `ONNE_1>`). `StreamReidentifier` holds back a possible pseudonym prefix until it is complete, and releases what is left just before `content_block_stop`. Tool inputs streamed as `input_json_delta` are restored with JSON escaping.

## Measured quality

`make benchmark` runs the detectors on the synthetic data set in `datasets/pii-fr` (backlog E4). Strict match on the development set: recall 1.0 on identifiers with a key and contact data, 0.99 on person names; organisations at recall 0.89 and precision 0.39; no hard negative reported. The detectors were tuned on that set, so these figures say little about other document layouts. Details and caveats: [`datasets/README.md`](../datasets/README.md).

## Limits

- Names and addresses depend on the model: recall on them is lower than on identifiers with a key, and E4 publishes the figures.
- A value the detectors miss reaches the model. The policy then refuses a request in which an identifier with a valid key is still in clear text (`not-pseudonymised`), and Bedrock Guardrails can mask what is left (`infra/terraform/modules/bedrock-guardrail`, E3.6), irreversibly.
- The spaCy model `fr_core_news_md` is distributed under LGPL-LR (licence of its French treebank source); it is downloaded at build time, not stored in this repository.

## Tests

```bash
make test-pseudo   # check digits, detectors, vault, request and stream re-identification
make up e2e down   # canaries through the gateway, buffered and streamed (gateway/tests/test_e2e_pseudo.py)
```
