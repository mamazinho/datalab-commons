lint:
	@uv run pre-commit install
	@uv run pre-commit run -a -v

test:
	@uv run pytest --cov --cov-report=term-missing -ra

update-deps:
	@uv sync --upgrade
	@uv lock --upgrade

delete_pycache:
	@find . -type d -name "__pycache__" -exec rm -rf {} +
