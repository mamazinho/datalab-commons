.PHONY: help lint test update-deps delete_pycache release

# A lib não tem deploy: a release é a tag. Os dois serviços fixam `@vX.Y.Z` no pyproject, e a
# versão do pacote sai da própria tag (hatch-vcs), então não há número para bumpar aqui.
NEXT_TAG = $(shell ./scripts/next-tag.sh $(type))

# `no-commit-to-branch` reprova qualquer coisa rodando na main — e a release sai da main por
# desenho. Os outros hooks seguem valendo.
RELEASE_SKIP_HOOKS = no-commit-to-branch

help: ## Mostra os comandos disponíveis
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

lint: ## Roda o pre-commit em todos os arquivos
	@uv run pre-commit install
	@uv run pre-commit run -a -v

test: ## Roda a suíte com cobertura
	@uv run pytest --cov --cov-report=term-missing -ra

update-deps: ## Atualiza as dependências
	@uv sync --upgrade
	@uv lock --upgrade

delete_pycache:
	@find . -type d -name "__pycache__" -exec rm -rf {} +

release: ## Publica uma versão da lib (Ex: make release type=fix, ou feat/major)
	@if [ -z "$(type)" ]; then \
		echo "❌ Informe o tipo. Ex: make release type=fix (ou feat/major)"; exit 1; \
	fi
	@if [ -n "$$(git status --porcelain)" ]; then \
		echo "❌ Árvore suja: a tag apontaria para algo diferente do que está commitado."; exit 1; \
	fi
	@if [ "$$(git rev-parse --abbrev-ref HEAD)" != "main" ]; then \
		echo "❌ Release sai da main (você está em $$(git rev-parse --abbrev-ref HEAD))."; exit 1; \
	fi
	@git fetch --quiet origin main
	@if [ "$$(git rev-parse HEAD)" != "$$(git rev-parse origin/main)" ]; then \
		echo "❌ Sua main difere da origin/main. Dê pull/push antes de taguear."; exit 1; \
	fi
	@echo "🧪 Validando antes de publicar — uma release quebrada quebra as duas APIs..."
	@$(MAKE) --no-print-directory test
	@SKIP=$(RELEASE_SKIP_HOOKS) uv run pre-commit run -a
	@echo "🏷️  Publicando $(NEXT_TAG)..."
	@git tag -a $(NEXT_TAG) -m "Release $(NEXT_TAG)"
	@git push --quiet origin $(NEXT_TAG)
	@echo "✅ $(NEXT_TAG) publicada."
	@echo
	@echo "   Para os serviços consumirem, atualize o pyproject de cada um:"
	@echo "   datalab-commons[...] @ git+https://github.com/mamazinho/datalab-commons.git@$(NEXT_TAG)"
	@echo "   e rode: uv lock --upgrade-package datalab-commons && uv sync"
