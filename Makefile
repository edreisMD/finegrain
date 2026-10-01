GBRAIN_REPO ?= https://github.com/garrytan/gbrain.git
GBRAIN_REF  ?= e78f1c3
GBRAIN_DIR  ?= vendor/gbrain
PY          := .venv/bin/python
PART2_DIR   := night/gm-nightly-loop
PART2_PY    := $(PART2_DIR)/.venv/bin/python
GM_NIGHT_CONFIG ?= $(PART2_DIR)/examples/gm-part2.toml
ENV         := set -a; [ -f .env ] && . ./.env; set +a;

.PHONY: setup data routing behavior pairs train bench test quickstart part2-setup part2-demo part2-test night

setup: $(GBRAIN_DIR)
	test -x .venv/bin/python || uv venv -q
	uv pip install -q -r requirements.txt

$(GBRAIN_DIR):
	git clone -q --filter=blob:none $(GBRAIN_REPO) $(GBRAIN_DIR)
	git -C $(GBRAIN_DIR) checkout -q $(GBRAIN_REF)

data: $(GBRAIN_DIR)
	GBRAIN_DIR=$(GBRAIN_DIR) $(PY) data/parse_skills.py

routing: data
	$(ENV) GBRAIN_DIR=$(GBRAIN_DIR) $(PY) data/make_routing.py

behavior: data
	$(ENV) GBRAIN_DIR=$(GBRAIN_DIR) $(PY) data/make_behavior.py

pairs: routing behavior

train:
	$(ENV) $(PY) train/train_gm.py

MODELS ?= Base + resolver,Base,GM

bench: data
	$(ENV) GBRAIN_DIR=$(GBRAIN_DIR) $(PY) bench/run_bench.py --models "$(MODELS)"

test:
	$(PY) -m pytest -q tests

quickstart:
	$(MAKE) setup
	$(MAKE) data
	$(MAKE) test
	$(MAKE) part2-demo
	$(MAKE) part2-test

part2-setup:
	$(MAKE) -C $(PART2_DIR) setup

part2-demo: part2-setup
	$(MAKE) -C $(PART2_DIR) demo

part2-test: part2-setup
	$(MAKE) -C $(PART2_DIR) test

night: part2-setup
	$(PART2_PY) night/run.py --config $(GM_NIGHT_CONFIG)
