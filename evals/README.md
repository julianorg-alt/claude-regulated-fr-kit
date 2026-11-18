# Evaluation in French

Backlog E6. 80 tasks in four sectors, plus a hold-out set of 20 (see below), (banking, insurance, health administration, public sector), run with [promptfoo](https://www.promptfoo.dev/) 0.125.1, pinned in `package-lock.json`. CI replays recorded answers and verdicts, so it needs no model and no key. `make eval-live` runs the same tasks on a real model with your own credentials.

## What is in it

| Path | Content |
|---|---|
| `tasks/holdout/<sector>.yaml` | hold-out set: 5 tasks per sector, 10 critical, reported and gated separately (see "Hold-out set") |
| `tasks/<sector>.yaml` | 20 tasks per sector: extraction to JSON, summaries, classification, replies in a professional register, missing-information checks, answers limited to a provided document. 24 tasks are marked `critical`: refusing personalised advice, not taking an individual decision, not inventing a missing rule or deadline, not disclosing a third party's data, routing an urgent message. |
| `prompts/assistant.json` | system prompt and task, the same for every model |
| `prompts/assistant.cached.json` | the same prompt with `cache_control` on the system block, used by `make eval-live` for Anthropic providers |
| `providers/cassette.py`, `providers/judge.py` | replay of answers (`cassettes/answers`) and judge verdicts (`cassettes/judge`) |
| `providers/negative.py`, `promptfooconfig.negative.yaml` | negative control |
| `assertions/` | shared French matchers (`fr.js`) and the two assertions built on them (`refusal.js`, `forbidden.js`) |
| `crfr_eval/` | report and gate, pass^k, Cohen's kappa, model comparison, cassette sealing and recording (standard library only) |
| `calibration/labels.example.csv` | format of the calibration labels, with invented values |

All documents in the tasks are fictional. They contain no real person, organisation or identifier, and every rule a task relies on is written into its document as an internal rule: the tasks test reading and restraint, not knowledge of French law.

## Graders, in this order

1. Code: every task has at least one assertion that a program checks (substring, JavaScript on the parsed JSON, regular expression). "The answer refuses", "the information is absent", "the service is not competent" and "the answer does not state this decision or advice" are never written as a list of phrases in a task: they go through the shared matchers of `assertions/` (see "Shared matchers"). The negative control proves they bite: a content-free answer must fail all 100 tasks (80 plus the hold-out), otherwise `make eval` fails.
2. LLM judge: 47 rubrics on the main tasks (every critical task has one next to its code checks) and 15 on the hold-out, one dimension each (`exactitude`, `fidelite`, `conformite`, `ton`). Each rubric starts with a tag `[grille <task>/<dimension>]` and lets the judge answer "INCONNU" when it cannot decide. The judge's prompt (`prompts/judge.json`) gives it the task and its source document, so INCONNU means a real doubt; the replay judge refuses a grading prompt without that `<Task>` block.
3. Human: a task whose only failing assertions are INCONNU verdicts is not counted as failed; the report lists it under "Sent to a human".

The gate (`python -m crfr_eval report`) fails on any error, on any failed critical task, and when the pass rate over decided tasks is below the threshold (1.0 on cassettes, 0.9 by default on a live run).

## The cassettes in this repository are hand-written

There is no model behind CI (decision K3: no AWS account). The answers in `cassettes/answers` are reference answers written for the tasks (`"source": "synthetic"`), and the judge verdicts in `cassettes/judge` are the verdicts those answers deserve, with four INCONNU on purpose to exercise the human path. They test the tasks, the graders and the tooling. They say nothing about how Claude performs. To measure a model, run `make eval-live`, then `make eval-record`: the cassettes then carry `"source": "recorded"`, the model and the date, and CI replays a real run.

A cassette is tied to what produced it: an answer is replayed only if the prompt has the same hash (canonical JSON), and a verdict only for the exact answer it graded. Changing a task without re-recording makes the run error instead of passing on stale data.

## JSON answers

The assistant prompt asks for raw JSON without code fences. Models still often wrap it in one fence, which is a formatting habit and not a wrong answer, so the assertions of the JSON tasks run on the output after `transforms/strip-json-fence.js`, which removes exactly one fence around the whole answer. Prose around the fence, two fences or an unclosed fence still fail.

The judge sees a JSON answer after that transform, in compact form (promptfoo joins the elements of an array with commas and drops the brackets). A judge verdict is therefore tied to that text (`judged_text`), so that `make eval-record` writes verdicts the replay finds again.

## Shared matchers

Three live runs showed that a keyword list per task keeps producing false negatives: each fix moved the problem. `assertions/fr.js` holds one tested rule for the class:

- `assertions/refusal.js` (`config.kind`: `refusal`, `absent` or `competence`): negation with up to three words in between ("nous ne pouvons donc ni vous donner"), first person singular and plural, "ne ... aucun(e)", "ne ... pas en mesure", "n'est pas précisé", "aucune clause". `config.also` lists the few task-specific plain words that are also accepted.
- `assertions/forbidden.js` (`config.patterns`): a forbidden decision or piece of advice ("est accordée", "vous pouvez doubler") fails only when the answer states it. It is ignored inside a refusal, inside an "if" or "whether" clause and in a disjunction. The judge rubric stays the primary grader of critical tasks.
- Privacy guards (health data, balances, identities, dates of a third party) are not negation aware and stay strict `not-icontains` checks. Do not move them to `forbidden.js`.
- Wording that has synonyms ("médecin prescripteur" and "le médecin qui vous a prescrit") is accepted through the judge rubric or an explicit synonym list written in the task.

`tests/test_matchers.py` runs the matchers on real model outputs from the live runs (must pass) and on answers that are not refusals (must fail). When a live run shows a new wording that is correct, add it to that test first, then fix the matcher.

## Hold-out set

`tasks/holdout/` holds 20 more fictitious tasks (5 per sector, 10 critical, at least 2 critical per sector), written from the sector rules and not from the outputs that failed in the live runs. Their ids are `holdout-<sector>-NN` and they carry the variable `set: holdout`. They exist to see whether a prompt change that fixes the main tasks also helps tasks it was not tuned on, or only fits the 80 it was tuned on.

- CI replays them like the others, from hand-written cassettes (`source: synthetic`), and the negative control must fail them too.
- `make eval-live` runs them in the same pass. The report shows them in their own section ("Hold-out"), with their own pass rate, pass^k, critical failures and gate line, and the main figures never include them (so the main figures stay comparable with earlier runs). The gate fails if the main set or the hold-out set fails: a critical failure, an error, or a pass rate under the threshold.
- Third pass (2026-11-17): four hold-out failures of run 3 were assertion bugs (refusals written with "donc", "ni" or "aucune" between the words), not prompt tuning. Their assertions were fixed by the shared matchers, documented in the triage file ("Troisième passage"). The prompt change of that pass (never offer to contact a third party whose existence the service must neither confirm nor deny) was decided from the main set only (public-09).
- **The hold-out is now frozen**: its tasks, assertions and cassettes do not change again, and it decides no prompt change, until a new hold-out is written from the sector rules.
- Rule: the hold-out is never used to tune the prompt. Read its result, do not read its failing outputs to write a prompt sentence. When a hold-out result is used to decide a prompt change, the set is spent: replace it with new tasks written from the rules and record the replacement in the triage document.

## Live runs

Five live runs (2026-11-17, Sonnet 5.5, judge Opus 5.5, K=3). What was a model defect, an over-strict assertion or variance is decided task by task in `docs/evals/triage-2026-11-17.md`. The full results, costs, token counts and the changes between runs are in [docs/evals/live-results-2026-11-17.md](../docs/evals/live-results-2026-11-17.md). Decided pass rate on the main set: 0.7814, 0.9264, 0.974, 0.9827, then 0.9957 (critical tasks 0.5833, 0.75, 0.875, 0.9167, then 1.00; pass^3 0.95 in run 5). Hold-out: 0.9333 (critical 0.80) in run 3, 0.9667 (critical 0.90) in runs 4 and 5. The gate was closed by critical failures in runs 1 to 4 and passed on the main set in run 5; on the hold-out it stays closed on holdout-sante-01, a documented residual defect.

### Prompt caching

For an `anthropic:` provider, `make eval-live` sends `prompts/assistant.cached.json` (same system prompt, one `cache_control: ephemeral` marker on the system block); `EVAL_PROMPT=file://prompts/assistant.json` turns it off. Bedrock keeps the plain prompt. The cassette hash ignores the marker, so replay is unchanged. Whether the cache is hit is to be read in the token usage of the next live run.

## Commands

```bash
make eval                                   # cassettes + negative control (part of make ci)
AWS_REGION=eu-west-3 make eval-live         # Bedrock, eu. profile, your AWS credentials; K=3 repeats
make eval-live EVAL_PROVIDER=anthropic:messages:claude-sonnet-5 EVAL_GRADER=anthropic:messages:claude-opus-5-5
make eval-record                            # results/run-live.json -> cassettes, review the diff
make eval-compare OLD=results/a.json NEW=results/b.json
make eval-calibrate LABELS=calibration/labels.csv
```

The Anthropic API offers no EU-only processing (`inference_geo` is `global` or `us`, verifications.md V13). Use it only on these synthetic tasks, never with real documents.

promptfoo runs with `PROMPTFOO_DISABLE_TELEMETRY=1` and `PROMPTFOO_DISABLE_UPDATE=1`, and npm installs it with install scripts disabled (`.npmrc`). `npm audit` reports advisories in promptfoo's dependency tree at this version; the tool runs offline in CI on files of the repository, never as a service.

## Calibration of the judge (E6.4)

Before trusting a judge, two people label the same sample of answers (`oui`, `non`, `inconnu`) for each dimension, in a CSV with the columns `task_id,dimension,judge,human_a,human_b`. `make eval-calibrate` computes Cohen's kappa for judge against the first annotator and for the two annotators, and fails under 0.6. If the two people do not agree with each other, the rubric is the problem, not the judge. `labels.example.csv` only shows the format: its values are invented.

## Reliability: pass^k

`make eval-live` repeats each task K times (`--repeat`). The report gives pass^k as defined by τ-bench (arXiv 2406.12045): for a task run n times with c successes, C(c, k) / C(n, k), averaged over tasks; and the same over critical tasks only. pass^1 is the success rate; pass^k drops when a model succeeds only some of the time, which is what matters for a task that must never go wrong.

## Changing model (E6.5)

1. Run `make eval-live` with the current model and keep `results/run-live.json` as the reference.
2. Run it with the candidate model (`EVAL_PROVIDER=...`), with the same K and the same grader.
3. `make eval-compare OLD=<reference> NEW=<candidate>` fails if a task is missing, if a critical task that passed now fails, or if the pass rate falls. Look at every regression listed, critical or not.
4. Recalibrate the judge if the grader model changes.
5. Record the candidate's cassettes (`make eval-record`) in the same change as the model switch, so that CI replays the model in use.
