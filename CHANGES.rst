Changelog
=========

0.7.0 (2026-11-05)
------------------

- Novo ``datalab_commons.censor.Censor``: troca por ``*****`` senha, token, código de confirmação,
  chave de API, cookie, credencial em URL e a query/parâmetros que o SQLAlchemy põe na mensagem do
  erro. É o mesmo tratamento para log e para resposta de erro.
- Novo módulo ``datalab_commons.errors``: o contrato ``ErrorResponse`` (``error``, ``status``,
  ``message``, ``friendly_message``, ``detail``), a base ``FriendlyException``, os handlers
  ``FriendlyErrorHandler.defaults()`` para o ``exception_handlers`` do FastAPI e o
  ``UnhandledErrorMiddleware``, que responde o 500 no contrato e precisa ficar dentro do CORS. A
  exceção levantada com ``from`` loga a original com traceback e só a devolve em ``detail.cause``
  quando o logging está em DEBUG (``LOG_LEVEL=DEBUG``). No 422, o ``friendly_message`` sai do tipo do erro do Pydantic, com o limite
  que ele traz ("Um dos campos precisa ter ao menos 3 caracteres."), ou do texto do ``ValueError``
  do validador.
- ``UpstreamError`` e ``UpstreamUnreachable`` passam a ser ``FriendlyException``. O texto do erro
  vai para ``message``; ``detail`` vira um objeto com o serviço, o status e o corpo dele. O
  ``UpstreamUnreachable`` recebe só o nome do serviço: a causa vem pelo ``from``. Quando o
  outro serviço responde no contrato, o ``friendly_message`` dele é repassado.
- O ``RequestLoggingMiddleware`` loga também o começo do request ("Request started"). Os dois logs
  levam método, ``http_path`` (a rota como chegou, com a query censurada), o ``traceparent``, os
  nomes dos headers e o corpo censurado pelo ``Censor`` (até 10 KB; binário aparece só com o tipo).
  O ``http_route`` deixa de existir. O "Request completed" sai em ``warning`` para 4xx e em
  ``error`` para 5xx ou exceção. Corpo binário (upload) segue direto para a rota, sem ser lido.
- Entre serviços só se propaga o ``traceparent``: o Baggage do ``log_context`` ia para todo host
  chamado por httpx (OpenAI, MCP do usuário) e era aceito de qualquer cliente.
- A query das URLs dos spans (``http.url``, ``url.full``…) passa pelo ``Censor``; o scrubbing do
  Logfire não olha essas chaves. O ``Censor`` passa a parar o valor no ``?``, senão o primeiro
  parâmetro de uma URL ficava preso ao ``https:`` e escapava.
- ``APISettings.fastapi_kwargs`` devolve só os caminhos de docs, ``None`` com ``DISABLE_DOCS=true``;
  ``title``, ``version``, ``debug`` e ``openapi_prefix`` saem, porque cada app declara os seus.
- ``errors`` exporta só ``FriendlyException``, ``FriendlyErrorHandler``,
  ``UnhandledErrorMiddleware`` e ``ErrorResponse``; ``ExceptionDescriber`` deixa de existir.
- A resposta passa a levar o trace no header W3C ``traceresponse``, no formato do ``traceparent``,
  no lugar do ``X-Trace-Id``. ``current_trace_id`` deixa de existir.

0.6.0 (2026-10-09)
------------------

- Atualiza versão minima do python para 3.14.8, mais recente até então.

0.5.0 (2026-09-24)
------------------

- Novo módulo ``datalab_commons.files`` (extra ``files``): ``extract_text`` converte docx, xlsx,
  pptx e texto em markdown para o modelo que não lê o formato original; ``decode_text``,
  ``to_utf8``, ``guess_media_type``, ``normalize_filename`` e ``content_disposition`` cobrem o
  resto do manuseio de anexo.
- A versão passa a ser escrita no ``pyproject.toml`` e registrada neste arquivo; a tag sai dela.

0.4.0 (2026-08-24)
------------------

- Mesmo código da 0.3.0.

0.3.0 (2026-08-24)
------------------

- O Logfire vira o destino único: sai o caminho do Grafana e as três settings dele.
- Todo serviço aceita ``traceparent`` de entrada; o argumento ``exposure`` deixa de existir.
- ``excluded_paths`` vale também para o log de conclusão, não só para o trace.

0.2.0 (2026-08-24)
------------------

- Mensagens de log em inglês.
- ``make release`` publica a lib por tag, validando testes e lint antes.

0.1.0 (2026-08-24)
------------------

- Primeira versão: observabilidade compartilhada, ``BaseAPIClient``, ``APISettings``,
  ``to_snake_case`` e ``get_package_version``.
- ``UpstreamError`` carrega o ``upstream_status`` do serviço remoto; ``UpstreamUnreachable``
  cobre timeout, conexão recusada e DNS.
- A exposição do serviço é argumento de ``configure_observability``, não env var.
