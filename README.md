# arxiv-watcher

arXiv の新着論文を定期取得し、関心のある分野・キーワードでフィルタリングとスコアリングを行い、日次 Markdown レポートを生成するツールです。GitHub Actions で毎日レポートを更新し、その内容を GitHub Pages でブラウザから閲覧できるようにできます。

## What It Does

- arXiv API から新着論文を取得
- include / exclude キーワードで論文を絞り込み
- タイトル、abstract、カテゴリに応じて関連度をスコアリング
- 日次 Markdown レポートを `reports/` に保存
- 生成済みレポートを `docs/` に静的HTMLとして変換
- GitHub Actions で日次実行し、GitHub Pages に公開しやすい形で蓄積

## Project Layout

- `src/arxiv_watcher/`: CLI、本体ロジック、保存、レポート生成
- `config/queries.yaml`: 監視クエリとスコアリング設定
- `reports/`: 生成された日次 Markdown レポート
- `docs/`: GitHub Pages 用の静的サイト出力
- `scripts/build_pages.py`: `reports/` から `docs/` を生成するスクリプト
- `.github/workflows/daily.yml`: 毎日の取得・レポート生成・Pagesサイト更新

## Setup

Python 3.11 以上が必要です。

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

開発用パッケージも入れる場合:

```bash
pip install -e ".[dev]"
```

初期化:

```bash
arxiv-watcher init
```

作成されるもの:

- `config/queries.yaml`
- `data/arxiv.db`
- `logs/`
- `reports/`
- `templates/`

## Configuration

`config/queries.yaml` で取得条件とスコアリングを定義します。

```yaml
defaults:
  max_results: 50
  lookback_days: 2
  timezone: Asia/Tokyo
  report_top_n: 20
  summarize: true
  min_relevance_score: 1.0

scoring:
  title_keyword_weight: 3.0
  abstract_keyword_weight: 1.5
  keyword_rules:
    - keyword: "large language model"
      weight: 5.0
  category_rules:
    - category: "cs.CL"
      weight: 2.0

queries:
  - name: llm_core
    enabled: true
    search_query: "(cat:cs.CL OR cat:cs.LG OR cat:cs.AI)"
    include_keywords:
      - "large language model"
      - "llm"
      - "reasoning"
    exclude_keywords:
      - "protein"
      - "molecule"
    max_results: 50
    min_relevance_score: 2.0
```

ポイント:

- `include_keywords` が空なら全件通過
- `exclude_keywords` は 1 つでも一致したら除外
- `enabled: false` の query は実行対象外
- `max_results` と `min_relevance_score` は query ごとに上書き可能

## CLI

全パイプライン実行:

```bash
arxiv-watcher run --config config/queries.yaml
arxiv-watcher run --config config/queries.yaml --query llm_core
arxiv-watcher run --config config/queries.yaml --no-summarize
arxiv-watcher run --config config/queries.yaml --verbose
```

取得のみ:

```bash
arxiv-watcher fetch --config config/queries.yaml
```

レポート再生成:

```bash
arxiv-watcher report
arxiv-watcher report --run-id <RUN_ID>
```

要約のみ:

```bash
arxiv-watcher summarize --run-id <RUN_ID>
```

## LLM Summaries

要約は optional です。`.env.example` を `.env` にコピーして設定します。

```bash
cp .env.example .env
```

OpenAI 互換 API を使う場合:

```env
LLM_BACKEND=openai
OPENAI_API_KEY=sk-your-api-key-here
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
```

```bash
pip install -e ".[llm]"
```

ローカル LLM を使う場合:

```env
LLM_BACKEND=local
LOCAL_LLM_MODEL=gemma4
LOCAL_LLM_ENDPOINT=http://localhost:11434/api/generate
LOCAL_LLM_TIMEOUT=60
```

要約が実行される条件:

- `config/queries.yaml` で `summarize: true`
- `LLM_BACKEND=openai` の場合は `OPENAI_API_KEY` と `OPENAI_MODEL`
- `LLM_BACKEND=local` の場合は `LOCAL_LLM_MODEL`

条件がそろわない場合は要約だけスキップされます。

## Build The Pages Site

`reports/` にある Markdown レポートを `docs/` に HTML 化します。

```bash
python scripts/build_pages.py
```

出力されるもの:

- `docs/index.html`: レポート一覧
- `docs/reports/*.html`: 各日レポートの詳細
- `docs/assets/style.css`: サイト用スタイル

## GitHub Actions

同梱の `.github/workflows/daily.yml` は、毎日レポートを生成し、Pages 用の静的サイトも更新します。

処理内容:

1. リポジトリを checkout
2. Python 3.11 をセットアップ
3. `pip install -e ".[llm]"` を実行
4. `arxiv-watcher run` を実行
5. `python scripts/build_pages.py` で `docs/` を再生成
6. `reports/` と `docs/` をコミットして push

ワークフローは毎日 08:10 JST に実行され、`workflow_dispatch` でも手動実行できます。

## Notes

- `reports/` の Markdown は履歴として残ります
- `docs/` は公開用の生成物なので、レポートが増えるたびに更新されます
- SQLite DB `data/arxiv.db` はローカル保存用で、GitHub には含めません
