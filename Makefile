# claude-regulated-fr: one entry point for local work and CI.
SHELL := /usr/bin/env
.SHELLFLAGS := bash -euo pipefail -c
TOOLS := $(CURDIR)/.tools/bin
export PATH := $(TOOLS):$(PATH)
TF_DIRS := $(wildcard infra/terraform/modules/*)
EXAMPLES := $(wildcard infra/terraform/examples/*)
UV := uv run --quiet --group dev

.PHONY: demo tools lint test test-agents mcp-check redteam-selftest redteam redteam-report redteam-promptfoo redteam-live redteam-scheduled test-python test-pseudo benchmark test-eval eval eval-live traceability test-traceability eval-record eval-compare eval-calibrate test-guard test-terraform test-policy plan-offline inventory supply-chain secrets ci gateway-config exit-drill up e2e down

tools: ## install pinned, checksum-verified tools into .tools/bin
	scripts/install-tools.sh

lint: tools
	cd tools && $(UV) ruff check . ../gateway ../pseudonymisation ../evals ../agents && $(UV) ruff format --check . ../gateway ../pseudonymisation ../evals ../agents
	terraform fmt -check -recursive infra
	conftest fmt --check policy

test: test-python test-traceability test-pseudo test-guard test-eval eval test-agents mcp-check redteam-selftest test-terraform test-policy plan-offline supply-chain

test-python:
	cd tools && $(UV) pytest -q

test-pseudo: ## unit tests of the French pseudonymisation (detectors, vault, re-identification)
	cd pseudonymisation && $(UV) pytest -q

BACKEND ?= spacy
benchmark: ## detectors on the synthetic French PII data set (E4.3); BACKEND=gliner for the optional model
	cd pseudonymisation && for set in v1 v1-test; do $(UV) python -m crfr_pseudo.benchmark \
	  --data ../datasets/pii-fr/$$set.jsonl --out ../datasets/pii-fr/results --backend $(BACKEND); done

PROMPTFOO := cd evals && PROMPTFOO_DISABLE_TELEMETRY=1 PROMPTFOO_DISABLE_UPDATE=1 PROMPTFOO_FAILED_TEST_EXIT_CODE=0 \
	PROMPTFOO_CONFIG_DIR=.promptfoo npx --no-install promptfoo
EVAL_PROVIDER ?= bedrock:eu.anthropic.claude-sonnet-5
EVAL_GRADER ?= bedrock:eu.anthropic.claude-opus-5-5
K ?= 3
# Anthropic API providers get the system prompt with cache_control (about 300 calls resend it); Bedrock does not.
EVAL_PROMPT ?= $(if $(findstring anthropic:,$(EVAL_PROVIDER)),file://prompts/assistant.cached.json,file://prompts/assistant.json)

test-eval: ## unit tests of the evaluation scripts (report, pass^k, kappa, cassettes)
	cd evals && $(UV) pytest -q

evals/node_modules: evals/package-lock.json
	cd evals && npm ci --ignore-scripts --no-audit --no-fund && touch node_modules

eval: evals/node_modules ## replay the French evaluation from cassettes (E6.1), then the negative control
	$(PROMPTFOO) eval --no-cache --no-table -o results/run-ci.json
	cd evals && $(UV) python -m crfr_eval report results/run-ci.json --title "Evaluation (cassettes)" --out results/run-ci.md
	$(PROMPTFOO) eval -c promptfooconfig.negative.yaml --no-cache --no-table -o results/run-negative.json
	cd evals && $(UV) python -m crfr_eval negative results/run-negative.json

eval-live: evals/node_modules ## real model with your credentials: EVAL_PROVIDER, EVAL_GRADER, K repeats (AWS_REGION=eu-west-3)
	$(PROMPTFOO) eval --no-cache --no-table --prompts $(EVAL_PROMPT) --providers $(EVAL_PROVIDER) --grader $(EVAL_GRADER) --repeat $(K) \
	  -o results/run-live.json
	cd evals && $(UV) python -m crfr_eval report results/run-live.json --title "Evaluation ($(EVAL_PROVIDER))" \
	  --k $(K) --min-pass-rate 0.9 --out results/run-live.md

eval-record: ## turn results/run-live.json into the cassettes CI replays; review the diff before committing
	cd evals && $(UV) python -m crfr_eval record results/run-live.json --model "$(EVAL_PROVIDER)"

eval-compare: ## model migration (E6.5): make eval-compare OLD=old.json NEW=new.json
	cd evals && $(UV) python -m crfr_eval compare $(OLD) $(NEW)

eval-calibrate: ## agreement of judge and annotators (E6.4): make eval-calibrate LABELS=calibration/labels.csv
	cd evals && $(UV) python -m crfr_eval kappa $(LABELS)

test-agents: ## approval gate, destinations, MCP proxy, indirect injection bench and its published ASR (E7.3, E7.4, E8)
	cd agents && $(UV) pytest -q

mcp-check: ## the MCP registry loads and every Rule of Two sheet is consistent with it (E8.1, E8.4)
	cd agents && $(UV) python -m crfr_agents check

redteam-selftest: evals/node_modules ## the live indirect injection assertions catch an obedient agent and pass a refusing one
	$(PROMPTFOO) eval -c redteam/promptfooconfig.selftest.yaml --no-cache --no-table -o results/redteam-selftest.json
	cd agents && $(UV) python -m crfr_redteam selftest

redteam: evals/node_modules ## OWASP LLM red team of the gateway layer, against the running stack (E7.1)
	cd evals && PROMPTFOO_DISABLE_TELEMETRY=1 PROMPTFOO_DISABLE_UPDATE=1 PROMPTFOO_CONFIG_DIR=.promptfoo \
	  npx --no-install promptfoo eval -c redteam/promptfooconfig.yaml --no-cache --no-table -o results/redteam-gateway.json

redteam-report: ## publish the attack success rate of this version (agents/results/asr.json and asr.md)
	cd agents && $(UV) python -m crfr_redteam report

redteam-promptfoo: ## regenerate evals/redteam/indirect.yaml from agents/scenarios/indirect.toml
	cd agents && $(UV) python -m crfr_redteam promptfoo

redteam-live: evals/node_modules ## real model with your credentials (AWS_REGION=eu-west-3): OWASP preset, then indirect injection
	cd evals && PROMPTFOO_DISABLE_REMOTE_GENERATION=true PROMPTFOO_DISABLE_TELEMETRY=1 PROMPTFOO_DISABLE_UPDATE=1 \
	  PROMPTFOO_CONFIG_DIR=.promptfoo npx --no-install promptfoo redteam run -c redteam/promptfooconfig.live.yaml \
	  -o results/redteam-owasp.yaml
	$(PROMPTFOO) eval -c redteam/promptfooconfig.indirect.yaml --no-cache --no-table -o results/redteam-indirect-live.json

GARAK ?= python3
PYRIT ?= python3
GARAK_SPEC ?= probes.latentinjection.LatentInjectionTranslationEnFr,probes.latentinjection.LatentInjectionReport,probes.promptinject.HijackHateHumans
SCHED_OUT := $(CURDIR)/agents/scheduled/out
redteam-scheduled: ## garak probes and PyRIT multi-turn scenarios against the running stack (E7.2, scheduled workflow)
	mkdir -p $(SCHED_OUT)
	export REST_API_KEY="$$(python3 -I gateway/tests/access_token.py redteam)" XDG_DATA_HOME=$(SCHED_OUT)/xdg; \
	  $(GARAK) -m garak --target_type rest --generator_option_file agents/scheduled/garak-rest.json \
	  --spec $(GARAK_SPEC) --generations 1 --report_prefix crfr > $(SCHED_OUT)/garak.log 2>&1
	cp $(SCHED_OUT)/xdg/garak/garak_runs/crfr.report.* $(SCHED_OUT)/
	CRFR_TOKEN="$$(python3 -I gateway/tests/access_token.py redteam)" HOME=$(SCHED_OUT) \
	  $(PYRIT) -I agents/scheduled/pyrit_multiturn.py --out $(SCHED_OUT)/pyrit.json

traceability: ## regenerate docs/compliance/matrix.md from compliance/*.toml (E9.1)
	cd tools && $(UV) python -m crfr.traceability write

test-traceability: ## every control has a text and a test, every reference resolves, the matrix is current
	cd tools && $(UV) python -m crfr.traceability check

test-guard: ## unit tests of the gateway guard (quotas, budgets, kill switch, policy client)
	cd gateway/guard && $(UV) pytest -q

test-terraform: tools
	for d in $(TF_DIRS); do echo "== $$d"; (cd $$d && terraform init -backend=false -input=false >/dev/null && terraform validate && terraform test); done

test-policy: tools
	conftest verify -p policy/terraform
	conftest verify -p policy/gateway

plan-offline: tools ## plan the examples with fake credentials and check them with conftest
	for d in $(EXAMPLES); do echo "== $$d"; (cd $$d && terraform init -backend=false -input=false >/dev/null \
	  && terraform plan -input=false -var offline=true -out plan.bin >/dev/null \
	  && terraform show -json plan.bin > plan.json \
	  && conftest test -p $(CURDIR)/policy/terraform plan.json); done

inventory: ## refresh the Bedrock inventory from the public AWS model cards, then review the diff
	cd tools && $(UV) python -m crfr.bedrock_inventory fetch --out ../infra/inventory/bedrock-claude.json
	cd tools && $(UV) python -m crfr.bedrock_inventory routes --inventory ../infra/inventory/bedrock-claude.json \
	  --residency eu --out ../infra/inventory/routes-eu.json
	cd tools && $(UV) python -m crfr.bedrock_inventory routes --inventory ../infra/inventory/bedrock-claude.json \
	  --residency eu_plus_adequacy --out ../infra/inventory/routes-eu-plus-adequacy.json
	git diff --stat -- infra/inventory

supply-chain:
	cd tools && $(UV) python -m crfr.supply_chain ..

LOCAL_MODELS := claude-sonnet-5,claude-opus-5-5,claude-haiku-4-5
COMPOSE := docker compose -f gateway/compose.yaml
UP_FLAGS ?= --build # behind a TLS-inspecting proxy: build the images first, then make up UP_FLAGS=

GATEWAY_CONFIG_ARGS = --routes ../infra/inventory/routes-eu.json \
	  --models $(LOCAL_MODELS) --source-region eu-west-3 \
	  --backend-host fake-bedrock --backend-port 8080 --backend-plaintext \
	  --jwt-issuer http://keycloak:8080/realms/crfr \
	  --jwt-jwks-uri http://keycloak:8080/realms/crfr/protocol/openid-connect/certs \
	  --jwt-audience claude-gateway --jwt-required-group --guard-host guard \
	  --exit-provider local --exit-plaintext --exit-host fake-bedrock \
	  --exit-model claude-sonnet-5=exit-model-fr --exit-model claude-haiku-4-5=exit-model-fr-small

gateway-config: ## regenerate the local gateway configs (standby exit route, and the switch used by the exit drill)
	cd tools && $(UV) python -m crfr.gateway_config $(GATEWAY_CONFIG_ARGS) --exit-mode standby --out ../gateway/config/aigw.yaml
	cd tools && $(UV) python -m crfr.gateway_config $(GATEWAY_CONFIG_ARGS) --exit-mode switch --out ../gateway/config/aigw-switch.yaml

exit-drill: ## exit drill (E10.2) against the running stack: switch the aliases to the second provider, test, restore
	AIGW_CONFIG=aigw-switch.yaml $(COMPOSE) up -d --no-build --force-recreate --no-deps --wait aigw
	status=0; python3 -I -m unittest discover -s gateway/tests -p 'drill_exit_switch.py' -v || status=$$?; \
	$(COMPOSE) up -d --no-build --force-recreate --no-deps --wait aigw; exit $$status

up: ## start the local stack: gateway, fake Bedrock, Keycloak (fails first if a host port is taken)
	python3 -I scripts/portcheck.py preflight
	$(COMPOSE) up -d $(UP_FLAGS) --wait

e2e: ## end-to-end tests against the running stack
	python3 -I -m unittest discover -s gateway/tests -p 'test_e2e*.py' -v

demo: up ## one command: start the local stack, then show what the gateway does to a prompt with personal data
	python3 -I scripts/demo.py

down:
	$(COMPOSE) down -v --remove-orphans

secrets: tools
	gitleaks detect --no-banner --redact --source .

ci: lint test secrets
