.PHONY: install test mypy run run-dry run-report clean

# ── instalacao ──

install:
	pip install -e .

# ── qualidade ──

test:
	pytest tests/ -v

mypy:
	mypy hfbrasil_preco/ tests/

# ── execucao ──

run:
	hfbrasil-preco

run-dry:
	hfbrasil-preco --dry-run -v

run-report:
	hfbrasil-preco-report --help

# ── limpeza ──

clean:
	rm -rf .mypy_cache .pytest_cache *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
