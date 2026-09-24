Changelog
=========


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
