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

Um `logfire.configure()` alimenta dois destinos:

| Destino | Recebe | Para quê |
|---|---|---|
| **Grafana / Loki** | logs de aplicação | log primário: startup, requisições, erros |
| **Grafana / Tempo** | spans de HTTP, banco, httpx, MCP | latência e dependências |
| **Logfire** | tudo, inclusive as conversas dos agentes | debug de prompt, tool call e token |

O `trace_id` aparece em toda linha do Loki e é o mesmo do Logfire — é por ele que se pula de um
para o outro. Os spans do scope `pydantic-ai` não saem para o Grafana: o texto das conversas é
quase todo o volume, e mantê-lo só no Logfire é o que segura a cota.

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
LOGFIRE_TOKEN=

GRAFANA_OTLP_ENDPOINT=https://otlp-gateway-<zona>.grafana.net/otlp   # vazio desliga o envio
GRAFANA_OTLP_HEADERS=Authorization=Basic <base64 de "instanceID:token">

CONSOLE_SPANS=true
CAPTURE_AI_CONTENT=true
TRACE_SAMPLE_RATE=1.0
DISTRIBUTED_TRACING=false   # true só em serviço interno, que recebe traceparent de confiança
```

## Desenvolvimento

```bash
make test
make lint
```
