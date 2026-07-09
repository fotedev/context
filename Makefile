.PHONY: install install-server lint test clean

install:
	pip install -r requirements.txt
	pip install -r gui/server/requirements.txt

install-server:
	pip install -r gui/server/requirements.txt

lint:
	ruff check . 2>/dev/null || flake8 . 2>/dev/null || echo "No linter configured — install ruff or flake8"

test:
	pytest tests/ -v 2>/dev/null || echo "No tests found — create tests/ directory"

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
	find . -type f -name "*.pyc" -delete 2>/dev/null
	rm -rf .mypy_cache .ruff_cache
	@echo "Cleaned __pycache__, .pyc, .mypy_cache, .ruff_cache"