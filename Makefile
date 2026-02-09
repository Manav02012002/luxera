.PHONY: clean test test-all

clean:
	python scripts/clean.py

test:
	pytest -q

test-all:
	pytest -q -m ""
