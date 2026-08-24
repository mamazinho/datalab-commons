# datalab-commons

Observabilidade e utilitários compartilhados entre a **Datalab API** e a **Datalab Core API**.

## Instalação

```toml
# pyproject.toml do serviço
dependencies = [
    "datalab-commons[sqlalchemy] @ git+https://github.com/<org>/datalab-commons.git@v0.1.0",
]

[tool.uv.sources]
datalab-commons = { path = "../datalab-commons", editable = true }
```

Extras: `sqlalchemy` para quem tem banco, `ai` para quem roda pydantic-ai.

## Observabilidade

Um `logfire.configure()`, um destino: o **Logfire** recebe os logs de aplicação como log, os spans
de HTTP, banco, httpx e MCP, e as conversas dos agentes.

Todo serviço aceita `traceparent` de entrada, então a requisição que sai do navegador, passa pela
Datalab API e chega à Core API é **um trace só**. Para isso valer, os serviços precisam apontar
para o mesmo projeto Logfire — o token é por projeto, e com dois projetos o trace chega partido.

### Uso

```python
from datalab_commons.observability import (
    configure_observability,
    instrument_agents,
    instrument_fastapi_app,
    log_context,
    get_logger,
)

configure_observability("meu-servico", "1.2.3")

app = FastAPI()
instrument_fastapi_app(app, engine=engine, excluded_urls=["/v1/health/"])
instrument_agents()
```

Campos permanentes no escopo e campos pontuais em uma linha:

```python
logger = get_logger(__name__)

with log_context(company_id=company.id, user_id=user.id):
    logger.info("Buscando ativos")                       # já carrega company_id e user_id
    logger.info("Ativo escolhido", asset_id=asset.id)    # + asset_id só nesta linha
```

`log_context` usa Baggage do OpenTelemetry, então os campos também viajam no header da requisição
e reaparecem nos spans do serviço chamado.

### Variáveis de ambiente

```bash
ENVIRONMENT=development
LOG_LEVEL=INFO
LOGFIRE_TOKEN=          # mesmo projeto em todos os serviços que compartilham trace

CONSOLE_SPANS=true
CAPTURE_AI_CONTENT=true
TRACE_SAMPLE_RATE=1.0
```

## Desenvolvimento

```bash
make test
make lint
```
