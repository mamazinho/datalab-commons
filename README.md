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
    logger.info("Buscando ativos")  # já carrega company_id e user_id
    logger.info("Ativo escolhido", asset_id=asset.id)  # + asset_id só nesta linha
```

Os campos do `log_context` ficam no processo: entre serviços só viaja o `traceparent`, que basta
para juntar tudo no mesmo trace. Baggage de quem chama é ignorado.

### Variáveis de ambiente

```bash
ENVIRONMENT=development
LOG_LEVEL=INFO
LOGFIRE_TOKEN=          # mesmo projeto em todos os serviços que compartilham trace

CONSOLE_SPANS=true
CAPTURE_AI_CONTENT=true
TRACE_SAMPLE_RATE=1.0
```

### Log de request

O `instrument_fastapi_app` instala o `RequestLoggingMiddleware`, que loga "Request started" e
"Request completed" com método, path, `traceparent`, os nomes dos headers e o corpo censurado pelo
`Censor` (até 10 KB; corpo binário, como upload, segue direto para a rota e aparece só com o tipo).
A resposta devolve o trace no header W3C `traceresponse`. A query das URLs nos spans do Logfire
também passa pelo `Censor`, porque o scrubbing dele não olha URL.

## Erros

Todo erro dos serviços sai no mesmo contrato, de 4xx a 5xx:

```json
{"error": "NomeDaExcecao", "status": 400, "message": "texto técnico", "friendly_message": "o que o usuário lê", "detail": {}}
```

```python
from datalab_commons.errors import FriendlyErrorHandler, FriendlyException, UnhandledErrorMiddleware

app = FastAPI(exception_handlers=FriendlyErrorHandler.defaults())
app.add_middleware(UnhandledErrorMiddleware)  # antes do CORSMiddleware, senão o 500 sai sem CORS
app.add_middleware(CORSMiddleware, ...)


class AgentNotFoundFriendlyException(FriendlyException):
    status_code = HTTPStatus.NOT_FOUND
    message = "Agent not found"
    friendly_message = "Agente não encontrado."
```

Cada serviço declara as próprias subclasses, levantadas só em service ou api. A levantada com
`raise ... from error` loga a original com traceback e, só com `LOG_LEVEL=DEBUG`, devolve ela em
`detail.cause`; fora disso o suporte acha a causa pelo trace.

No 422, o `friendly_message` vem do tipo do primeiro erro do Pydantic ("Um dos campos precisa ter
ao menos 3 caracteres."); tipo sem frase própria cai em "Os dados enviados são inválidos.". Num
`value_error`, o texto é o do `ValueError` do validador, então ele precisa estar em português.

## Dados sensíveis

`Censor` troca por `*****` o que não pode sair num log nem numa resposta: `Censor.censor(valor)`
percorre dict e lista mascarando as chaves sensíveis, e `Censor.censor_text(texto)` cobre texto
livre (`api_key=...`, `Bearer ...`, JWT, credencial em URL, query do SQLAlchemy).

## Arquivos

`datalab_commons.files` concentra as bibliotecas de manipulação de arquivo e expõe só as funções
que os serviços usam. Extra `files`.

```python
from datalab_commons.files import (
    content_disposition,  # header do download, com nome acentuado
    decode_text,  # bytes -> str (utf-8, cp1252, latin-1)
    extract_text,  # docx, xlsx, pptx e texto -> markdown, para o modelo que não lê o formato
    guess_media_type,  # content-type do navegador ou extensão do nome, Office incluso
    normalize_filename,  # nome seguro, com extensão e limite de 255
    to_utf8,  # reencoda só o que não é utf-8
)
```

Constantes de apoio: `IMAGE_MEDIA_TYPES`, `TEXT_MEDIA_TYPES`, `OFFICE_MEDIA_TYPES`,
`EXTRACTABLE_MEDIA_TYPES`, e os predicados `is_text_media_type`, `is_image_media_type` e
`is_office_media_type`. `extract_text` levanta `UnsupportedFileType` no formato que não sabe ler.

## Desenvolvimento

```bash
make test
make lint
```

## Release

A versão mora no `pyproject.toml` e cada uma tem sua seção no [CHANGES.rst](CHANGES.rst).

```bash
uv version --bump minor   # ou patch/major
# escreva a seção da nova versão no CHANGES.rst e faça o commit na main
make release              # publica a tag v<version> com as notas do CHANGES.rst
```
