.PHONY: clean test test-all gates perf release-check release-check-radiance

clean:
	python scripts/clean.py

test:
	pytest -q

test-all:
	pytest -q -m ""

gates:
	pytest -q tests/gates/test_gate_determinism.py tests/gates/test_gate_agent_approvals.py tests/gates/test_gate_failure_recovery.py

perf:
	python benchmarks/bench_bvh_occlusion.py

release-check:
	python scripts/release_gates.py

release-check-radiance:
	python scripts/release_gates.py --with-radiance-validation --require-radiance-validation
