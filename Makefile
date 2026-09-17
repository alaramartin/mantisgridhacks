# Adapted from MantisGrid's track-1/Makefile for this repo's layout: the starter
# lives at the repo root (Dockerfile + run.py at root, as docs/submission.md asks).
# Bundles live in data/<SET>/ -- see docs/GET_DATA.md.
SET ?= Market-cloudbed-1
OUT ?= out/dev
PY  ?= python
# which agent module run.py loads, e.g. AGENT=agents.routed (default: run.py's)
AGENT_ARG := $(if $(AGENT),--agent $(AGENT),)

.PHONY: help data validate dev score cost docker
.DEFAULT_GOAL := help

help:
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

data: ## download and unzip the Market-cloudbed-1 bundle into data/ (1.3 GB -> ~12 GB)
	mkdir -p data
	cd data && curl -O https://mantisgrid-hackathon.s3.us-east-1.amazonaws.com/track-1-Market-cloudbed-1.zip
	cd data && unzip -q track-1-Market-cloudbed-1.zip

validate: ## run your agent on 2 dev cases and check the output shape
	VAL_AGENT=$(or $(AGENT),agents.heuristic) $(PY) scripts/validate_submission.py --submission . \
	  --dataset data/$(SET) --queries data/$(SET)/dev/query_dev.csv

dev: ## run your agent over all 70 cases -> $(OUT)/ (N=20 for the first 20)
	$(PY) run.py --dataset data/$(SET) \
	  --queries data/$(SET)/dev/query_dev.csv --out $(OUT) $(AGENT_ARG) $(if $(N),--limit $(N),)

score: ## score $(OUT)/ against the answers
	$(PY) score.py --predictions $(OUT)/predictions.csv \
	  --queries data/$(SET)/dev/query_dev.csv

cost: ## dollars per case and per model for $(OUT)/, from its usage.jsonl
	$(PY) cost.py $(OUT)/usage.jsonl

docker: ## build the image and run 2 dev cases exactly as judges will, capped at 2 CPU / 8 GB
	docker build -t rca-submission .
	rm -rf out/docker && mkdir -p out/docker
	docker run --rm --cpus 2 --memory 8g -e FEATHERLESS_API_KEY -e FEATHERLESS_BASE_URL \
	  -v "$(CURDIR)/data/$(SET)":/data:ro -v "$(CURDIR)/out/docker":/out rca-submission \
	  python run.py --dataset /data --queries /data/dev/query_dev.csv --out /out --limit 2 $(AGENT_ARG)
	@ls out/docker/evidence | wc -l | xargs echo "evidence files:"
