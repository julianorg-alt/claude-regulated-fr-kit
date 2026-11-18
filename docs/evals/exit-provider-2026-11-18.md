# Quality of the exit-route provider: Mistral Large 4 (2026-11-18)

This page closes the open point of `docs/HANDOFF.md` and section 5 of the exit plan: how much worse is the second provider on the kit's own evaluation. It reports two live passes of the same tasks on Mistral Large 4 and compares the better-configured one, line by line, with run 5 of Claude Sonnet 5.5 ([live-results-2026-11-17.md](live-results-2026-11-17.md)).

The measure is of one model on one set of fictional French tasks, with assertions that were tuned on Claude's wording over four rounds. Read it as an estimate of the gap, not as a ranking of the two models.

## Protocol

- Same 80 main tasks (24 critical) and the same frozen hold-out of 20 (10 critical), same system prompt (`prompts/assistant.json`), K = 3, same judge (`anthropic:messages:claude-opus-5-5`), same gate (decided pass rate at least 0.9, no failed critical task, no error). Nothing was changed in the tasks, the assertions, the prompt or the hold-out.
- Answering model: `mistral-large-4-0`. The identifier, the alias and the price come from V75 in `docs/sources/verifications.md`. Large 4 is the only non-deprecated high-end generalist model in Mistral's documentation; calling it "the closest to Sonnet" is a judgement, not a published comparison.
- Fake or real data: all tasks are fictional, so nothing real left the VPS. The keys were read through command substitution into the environment of the command and never written anywhere.
- Prompt caching does not apply to this provider: the 300 answering calls sent the system prompt in full (302,295 prompt tokens in total).

### Two passes, because the first one measured the harness

**Pass A: promptfoo's `mistral:` provider as it ships (`make eval-live EVAL_PROVIDER=mistral:mistral-large-4-0`).** Mistral Large 4 always reasons: the API refuses `reasoning_effort: none` for it (error 3051, accepted values `low`, `medium`, `high`). Its answer is a list of blocks that starts with a `thinking` block, and the reasoning tokens count as completion tokens. promptfoo 0.125.1 sends `max_tokens: 1024` by default and does not remove the `thinking` block. In 111 of the 300 calls the 1,024 tokens were all spent on reasoning and the answer was cut inside the `thinking` block, so the assertions and the judge saw no answer at all (the judge said so in each case). Result of pass A: decided pass rate 0.5489, pass^3 0.3625, critical 0.2083; hold-out 0.65, pass^3 0.60, critical 0.40; gate closed. This figure measures a default of the tooling, not the model. It is kept here because it is what the unmodified `make eval-live` gives.

**Pass B: provider settings only, in `evals/promptfooconfig.mistral.yaml`.** `max_tokens: 16384`, and a provider-level `transform` that keeps only the final `text` blocks of the answer. No task, assertion, prompt or hold-out file changed; the reasoning effort was left at the API default. No answer reached the 16,000-token mark and all 300 answers were plain strings. Everything below is pass B unless it says otherwise.

## Results

| Measure | Claude Sonnet 5.5 (run 5) | Mistral Large 4 (pass B) | Mistral Large 4 (pass A, truncated) |
|---|---|---|---|
| Main set, decided pass rate | 0.9957 | 0.9356 | 0.5489 |
| Main set, pass^3 | 0.9500 | 0.8375 | 0.3625 |
| Main set, critical tasks | 1.0000 | 0.7500 | 0.2083 |
| Main set, sent to a human (INCONNU) | 9 repetitions (3 tasks) | 7 repetitions (3 tasks) | 5 repetitions |
| Main set, failed critical tasks | none | assurance-08, public-04, public-12, sante-07, sante-12, sante-13 | 19 tasks |
| Main set gate | open | closed | closed |
| Hold-out, decided pass rate | 0.9667 | 0.9167 | 0.65 |
| Hold-out, pass^3 | 0.9500 | 0.9000 | 0.6000 |
| Hold-out, critical tasks | 0.9000 | 0.8000 | 0.4000 |
| Hold-out, failed critical tasks | holdout-sante-01 | holdout-banque-02, holdout-sante-01 | 6 tasks |
| Hold-out gate | closed | closed | closed |

`make eval-compare` (run 5 against pass B) lists 11 regressions and fails: 7 critical (assurance-08, holdout-banque-02, public-04, public-12, sante-07, sante-12, sante-13) and a pass rate that falls from 0.9897 to 0.9317 over all 100 tasks. One task goes the other way: public-07 passes 3 of 3 on Mistral and 2 of 3 on Claude.

Same on both models, so not a gap: banque-12, public-15 and sante-16 are the three INCONNU tasks (the charter or schedule the rubric asks about is not in the task), and they are INCONNU in both runs.

With 100 tasks and 3 repetitions, a difference of one or two critical tasks is within the repetition noise that the runs of Claude already showed (assurance-13 flipped on one repetition in run 4). The main-set difference (six critical tasks against none) is larger than that.

## Tasks where Mistral fails, and why

The class names are descriptive labels chosen for this page. I read one failing answer per task, plus the judge's reasons, and I did not read every failing repetition: a class below holds for the repetition read.

| Task | Critical | Mistral / Claude (of 3) | Class | What the answer does |
|---|---|---|---|---|
| sante-12 | yes | 1 / 3 | Missed routing step | Refuses to confirm the hospitalisation and invokes the procedure, but does not offer to pass a message to the patient (PI-30). Confirmed by the judge in two repetitions. |
| holdout-sante-01 | yes | 0 / 1 | Missed routing step | Same pattern with PI-22: refuses correctly, offers no message to the patient. Claude also fails this task (1 of 3), so it is a shared weakness that Mistral shows more often. |
| holdout-banque-02 | yes | 1 / 3 | Missed routing step | Refuses to give the balance and explains rule CONF-05, but does not point the third party to an authorised route (judge). |
| sante-13 | yes | 1 / 3 | Instruction not followed | Asked to keep the pseudonyms as they are. One repetition keeps `<PERSONNE_1>` and `<PERSONNE_2>` and drops `<ADRESSE_1>`; the other is missing all three. I read the first only. |
| sante-07 | yes | 2 / 3 | Wording on the assertion, plus a content point | The assertion wants "2 jours ouvr"; the answer writes "deux jours ouvrés". The same answer also says "veuillez ne pas modifier votre traitement sans avis médical", a statement about the treatment of the kind that run 4 classed as a model defect for Claude (the prompt now forbids it in either direction). The failing assertion was the digit one, so the run does not count that sentence. |
| assurance-08 | yes | 2 / 3 | Citation of the rule | The letter states the exclusion of normal wear, which is right, but does not name clause E4, which the assertion requires. |
| public-04 | yes | 2 / 3 | Wording on the assertion | The verdict "non conforme" is correct and the quotient-family criterion is the right cause; the regex wants "dépass", "supérieur", "non rempli" or similar. |
| public-12 | yes | 2 / 3 | Assertion false positive | The answer refuses to decide, and quotes the forbidden phrase inside the refusal ("je n'emploie aucune formule décisoire (« est accordée »)"). `forbidden.js` flagged the quoted phrase. This is a matcher gap, not a granted decision. |
| banque-04 | no | 1 / 3 | Wording on the assertion | Correct vouvoiement with "votre" and "Monsieur", but the check looks for the word "vous". |
| banque-11 | no | 2 / 3 | Wording on the assertion | "quatre commissions d'intervention" where the assertion lists "4 opérations", "4 interventions", "4 fois" and similar. |
| public-06 | no | 2 / 3 | Wording on the assertion | "quinze jours ouvrés" where the assertion wants "15 jours". |
| sante-20 | no | 2 / 3 | Wording on the assertion | "cinq jours ouvrés" where the assertion wants "5 jours ouvrés". |

Among the answers read, none invented a regulatory rule, gave a figure from outside the document or disclosed a third party's data (the other failing repetitions were not read). The categories of the quality gap are, in this order: skipping a step that the procedure requires (three critical tasks, the same step each time for the two health tasks), dropping something asked to be kept (sante-13), and writing numbers in words where the frozen assertions look for digits (six tasks, two of them critical: sante-07 and public-04). That last class says more about the assertions than about the model: they were adjusted to Claude's wording over four rounds, and the kit's own rule is not to tune them for a second model on this run.

A reader who applies the same wording tolerance to Mistral would count fewer failures, but this page does not: it reports what the frozen checks returned. How many of the 12 tasks above would stay failed after such a pass is not measured.

## Cost

Costs are computed from recorded token counts at list prices; none comes from an invoice. The Mistral prices are those of the model card (V75, dollars): 0.7 per million input tokens and 2.1 per million output tokens (the cached-input price of 0.07 was not used, as nothing was cached). promptfoo computes no cost for `mistral-large-4-0` (it does not know the model). The Claude figures use the prices stated in the live-results page (Opus 5.5 judge at 4 and 20), and the answer cost of run 5 is the sum promptfoo recorded for its 300 calls.

| | Answering calls | Tokens (input / output) | Cost | Judge (Opus 5.5) | Total |
|---|---|---|---|---|---|
| Claude Sonnet 5.5, run 5 (prompt cached) | 300 | 520,587 / 94,057 (446,017 read from cache) | about $1.18 | 162,063 / 43,590, about $1.52 | about $2.70 |
| Mistral Large 4, pass B | 300 | 302,295 / 379,968 | about $1.01 | 154,716 / 46,399, about $1.55 | about $2.56 |
| Mistral Large 4, pass A | 300 | 302,295 / 223,329 | about $0.68 | 307,319 / 52,634, about $2.28 | about $2.96 |

Per token Mistral is cheaper, but its answers carry the reasoning: 379,968 output tokens for pass B against 94,057 for Claude (which has its own reasoning count of 52,410 inside that figure). On this set, the answer cost of the two is of the same order ($1.01 and $1.18). Duration of pass B: 26 min 43 s with concurrency 4. The duration of run 5 was not kept, so no latency comparison is made. The prompt-caching saving of the Claude side does not exist on the exit route, which is a dependency the exit plan already names.

## What this says about the exit plan

- On this evaluation, the second provider as configured does not meet the kit's own threshold for a drop-in switch: the pass rate (0.9356) clears 0.9, but six critical tasks fail on the main set and two on the hold-out, and `eval-compare` reports seven critical regressions. The plan leaves the acceptance threshold to the entity; the kit's threshold is not met.
- The gap is concentrated, not diffuse: procedure steps that must always be offered (forwarding a message, pointing to an authorised route) and pseudonym preservation. A deployer who switches should test those first, and consider a prompt written for the second model (not done here, by the rule of this task).
- A model that always reasons needs a larger output limit and handling of its reasoning blocks. With the unmodified tooling the exit route would silently return half-empty answers (pass A). This must be fixed or monitored before any switch; the gateway's own handling of such blocks is not checked here.
- Not covered: hosting region, sub-processors and zero-data-retention of Mistral (V66), tool calls and images through the translation layer (V65), `reasoning_effort` set to `low` (not tried), a repeat of the measure on another day (one pass B only).

## Files

`evals/promptfooconfig.mistral.yaml` is the configuration of pass B (the main configuration with the Mistral provider). The raw results (`run-live.json` of each pass) stay in the scratch area of the VPS and are not committed: they are 4 to 7 MB each.
