# Contributing to EvalForge Maestro

Thank you for your interest in contributing to **EvalForge Maestro**!

Please read our [Code of Conduct](CODE_OF_CONDUCT.md) before participating. To report a security vulnerability, follow [SECURITY.md](SECURITY.md) instead of opening a public issue.

---

## Project Scope & Architectural Guardrails

EvalForge Maestro is an **independent evaluation and regression verification engine**—never an LLM runtime, RAG indexer, or agent framework (see [`docs/intent.md`](docs/intent.md) and [`docs/future-features.md`](docs/future-features.md)).

Before proposing a major feature or refactor, please open an issue so we can align on scope. All pull requests must preserve these core engineering invariants:

1. **Three-Way Separation of Concerns**: Keep **Evaluation** (scoring + evidence decoupling diagnostics), **Regression** (baseline/cohort comparison, trends, anomalies, drift), and **Acceptance** (`QualityGate`) strictly separated.
2. **Library Purity & Cold-Start Isolation**: Core library packages (`types`, `datasets`, `execution`, `storage`, `metrics`, `judges`, `embeddings`, `regression`, `reporting`) must never import CLI modules, read `evalforge.toml`/`.env` files directly, or eagerly import optional dependencies (`litellm`, `docpipe_maestro`, `numpy`, `scipy`, `sqlite3`, `http.server`). Enforced by [`tests/test_library_purity.py`](tests/test_library_purity.py).
3. **Single Schema Source & API Stability**: All Pydantic v2 data contracts live in [`src/evalforge_maestro/types.py`](src/evalforge_maestro/types.py). Preserve backward compatibility for persisted `.evalforge/` artifacts and pinned public exports in [`tests/test_api_stability.py`](tests/test_api_stability.py).
4. **Hermetic Offline Tests**: Unit, contract, and integration tests must run offline without live network requests or ambient `EVALFORGE_*`/provider environment variables.

---

## Development Setup

EvalForge Maestro targets **Python 3.10–3.13** and manages dependencies with [`uv`](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/ivnmoreno/evalforge-maestro.git
cd evalforge-maestro
uv sync --frozen --extra dev
```

To test optional integrations locally:

```bash
uv sync --frozen --extra dev --extra judges
uv sync --frozen --extra dev --extra embeddings
uv sync --frozen --extra dev --extra docpipe-maestro
```

---

## Branching & Commit Conventions

1. Branch from an up-to-date `main`:
   ```bash
   git checkout main && git pull --ff-only
   git checkout -b feat/short-description
   ```
2. Follow **Conventional Commits** (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`, `ci:`). CI validates commit messages with Commitizen (`cz check`):
   ```bash
   uv run cz check --rev-range main..HEAD
   ```
3. Keep pull requests focused on a single logical change and update documentation and tests alongside code edits.

---

## Local Verification Checklist

Run the same checks enforced by [`.github/workflows/ci.yml`](.github/workflows/ci.yml) before opening a pull request:

```bash
# Lockfile freshness
uv lock --check

# Formatting, lint, and Bandit security rules
uv run ruff format --check .
uv run ruff check .
uv run ruff check --select S src/

# Strict static type checking
uv run mypy --strict src tests

# Full test suite (>=85% branch coverage)
uv run pytest --strict-markers -W error \
  --cov=evalforge_maestro --cov-branch --cov-fail-under=85

# 100% branch coverage on deterministic metrics and QualityGate
uv run pytest --strict-markers -W error \
  --cov=evalforge_maestro.metrics --cov-branch --cov-fail-under=100 \
  tests/unit/test_metrics.py \
  tests/unit/test_ir_metrics.py \
  tests/unit/test_agent_metrics.py \
  tests/contract/test_metric_formulas.py

uv run pytest --strict-markers -W error \
  --cov=evalforge_maestro.regression.gate --cov-branch --cov-fail-under=100 \
  tests/unit/test_quality_gate.py

# Mandatory determinism and immutability release gates
uv run pytest --strict-markers -W error -m "gate_determinism or gate_immutability"
```

---

## Reporting Bugs & Requesting Features

- **Bug reports**: Include your Python version, OS, `evalforge-maestro --version`, minimal reproduction steps/dataset snippet, and scrubbed error output (never paste real API keys or PII).
- **Feature requests**: Describe the evaluation or regression problem you are solving and why it fits EvalForge's standalone evaluation engine scope.

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
