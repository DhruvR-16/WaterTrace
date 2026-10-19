PYTHON ?= .venv/bin/python
NODE ?= node

.PHONY: verify reproduce

# Offline software checks; no account, download, deployment, or billing action.
verify:
	$(PYTHON) -m pip check
	$(PYTHON) -m pytest -q
	$(NODE) --check watertrace/static/app.js
	$(NODE) --check watertrace/static/model.js
	$(NODE) --test --test-reporter=dot tests/watertrace.test.cjs
	$(PYTHON) scripts/check_watertrace_lab.py
	git diff --check

# Requires the already-downloaded test cache. Use a NEW output directory.
# mkdir deliberately fails if it exists; never replace prior evidence.
OUT ?= artifacts/reproduction
reproduce:
	$(PYTHON) scripts/verify_watertrace_data.py --split test
	mkdir "$(OUT)"
	$(PYTHON) scripts/evaluate_watertrace.py --split test --experiments --output "$(OUT)/evaluation.json"
	$(PYTHON) scripts/audit_watertrace_uncertainty.py "$(OUT)/evaluation.json" --output "$(OUT)/uncertainty.json"
