.PHONY: setup validate doctor harness

setup:
	npm ci --ignore-scripts

validate:
	python3 .ai/scripts/check_setup.py
	node .ai/scripts/check_cezar.mjs

doctor:
	python3 .ai/scripts/doctor.py

harness:
	npm run harness
