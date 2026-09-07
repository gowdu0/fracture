# Contributing

Use Python 3.12 or 3.13 and uv:

```console
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
uv run fracture demo --output artifacts/contribution-demo
```

Keep changes small and behavior-driven. Recovery tests must preserve the
external-write/checkpoint gap and use real worker termination for crash claims.
Include negative controls for new assertions. Never count unsupported or unreached
faults as passes. Record dependency/version changes and rerun the semantics spike.

The MIT license applies to contributions. Do not commit credentials, actual
customer data, generated databases, or bulky run artifacts. Keep captured examples
synthetic and label planted defects. Public APIs are experimental at version 0.1.
