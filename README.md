# arxiv-watcher

arxiv-watcher is a small daily batch tool for collecting new arXiv papers, scoring them against configured interests, generating a Markdown digest, publishing a static report site, and optionally posting the digest to Discord.

The current repository is configured around LLM / reasoning / mathematical topics, but the watched categories, keywords, and scoring rules are all editable in `config/queries.yaml`.

## What It Produces

- Markdown daily digests in `reports/YYYY-MM-DD.md`
- A static GitHub Pages site under `docs/`
- A local SQLite run history in `data/arxiv.db`
- Optional Japanese LLM summaries and Discord notifications

## Quick Start

Python 3.11+ is required.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,llm]"
arxiv-watcher init
arxiv-watcher run --config config/queries.yaml
python scripts/build_pages.py
```

Common commands:

```bash
arxiv-watcher run --config config/queries.yaml
arxiv-watcher run --config config/queries.yaml --query llm_math
arxiv-watcher run --config config/queries.yaml --all
arxiv-watcher run --config config/queries.yaml --no-summarize
arxiv-watcher fetch --config config/queries.yaml
arxiv-watcher report --run-id <RUN_ID>
arxiv-watcher summarize --run-id <RUN_ID>
```

## Configuration

Edit `config/queries.yaml`.

- `queries[].search_query` is passed to the arXiv API.
- `include_keywords` keeps papers matching at least one keyword. If empty, all papers pass this step.
- `exclude_keywords` removes papers matching any keyword.
- `min_relevance_score` controls the score threshold per query.
- `scoring.keyword_rules` and `scoring.category_rules` define score weights.
- `enabled: false` queries are skipped unless `--all` is used.

The main pipeline is:

```text
fetch -> parse -> lookback/filter -> score -> save -> summarize -> report
```

## LLM Summaries

Summaries are optional. If no usable LLM configuration is present, the batch still runs and reports are generated without summaries.

OpenAI-compatible APIs:

```env
LLM_BACKEND=openai
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
```

Local Ollama-style `/api/generate` endpoint:

```env
LLM_BACKEND=local
LOCAL_LLM_MODEL=gemma3
LOCAL_LLM_ENDPOINT=http://localhost:11434/api/generate
LOCAL_LLM_TIMEOUT=60
```

## GitHub Actions

`.github/workflows/daily.yml` runs the watcher every day at 08:10 JST and can also be triggered manually. It:

1. installs the package,
2. runs `arxiv-watcher`,
3. rebuilds `docs/`,
4. commits `reports/` and `docs/`,
5. posts to Discord if `DISCORD_WEBHOOK_URL` is configured.

Required or optional secrets:

- `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`: optional, for OpenAI-compatible summaries
- `DISCORD_WEBHOOK_URL`: optional, for Discord notification

## Repository Layout

- `src/arxiv_watcher/`: package source
- `config/queries.yaml`: watch and scoring configuration
- `templates/daily_report.md.j2`: Markdown report template
- `reports/`: generated Markdown digests
- `docs/`: generated static site
- `scripts/build_pages.py`: builds `docs/` from `reports/`
- `scripts/post_to_discord.py`: posts the latest run to Discord
- `tests/`: unit tests
