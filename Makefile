.PHONY: setup validate lint typecheck test build doctor harness harness-verify demo-init serve

setup:
	npm ci --ignore-scripts
	uv sync --locked

validate:
	python3 .ai/scripts/check_setup.py
	node .ai/scripts/check_cezar.mjs
	uv lock --check
	$(MAKE) lint typecheck test build

lint:
	uv run --locked ruff check src tests scripts
	uv run --locked ruff format --check src tests scripts

typecheck:
	uv run --locked mypy

test:
	uv run --locked pytest

build:
	uv build

demo-init:
	uv run --locked agentgate init-demo

serve:
	uv run --locked agentgate serve

doctor:
	python3 .ai/scripts/doctor.py

harness:
	npm run harness

harness-verify:
	python3 .ai/scripts/cezar_verify.py
