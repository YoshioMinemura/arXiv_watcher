# 📚 arxiv-watcher

arXiv の新着論文を定期取得し、関心のある分野・キーワードで自動フィルタリング＆スコアリングして、日次 Markdown レポートを生成する CLI ツールです。

## ✨ 主な機能

- **arXiv 論文の自動取得**: arXiv API を使って新着論文を定期取得
- **キーワードフィルタリング**: include/exclude キーワードで関心分野を絞り込み
- **関連度スコアリング**: タイトル・要旨・カテゴリに基づく柔軟なスコアリング
- **日次 Markdown レポート**: 見やすいレポートを自動生成
- **LLM 日本語要約** (optional): OpenAI 互換 API による日本語要約・新規性分析
- **SQLite データベース**: 論文メタデータの永続化・重複除去
- **GitHub Actions 対応**: 毎日自動実行してレポートをコミット

## 🚀 セットアップ

### 1. リポジトリのクローン

```bash
git clone https://github.com/your-username/arxiv-watcher.git
cd arxiv-watcher
```

### 2. Python 環境の準備

Python 3.11 以上が必要です。

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate
```

### 3. インストール

```bash
pip install -e .
```

開発用パッケージ（テスト）も含める場合:

```bash
pip install -e ".[dev]"
```

### 4. 初期化

```bash
arxiv-watcher init
```

以下が作成されます:
- `config/queries.yaml` (サンプル設定)
- `data/arxiv.db` (SQLite データベース)
- `logs/`, `reports/`, `templates/` ディレクトリ

## ⚙️ 設定 (`queries.yaml`)

`config/queries.yaml` でクエリとスコアリングルールを設定します。

```yaml
defaults:
  max_results: 50          # 1クエリあたりの最大取得件数
  lookback_days: 2         # 何日前まで遡って取得するか
  timezone: Asia/Tokyo     # レポートのタイムゾーン
  report_top_n: 20         # レポートに載せる最大件数
  summarize: true          # LLM要約の有効/無効
  min_relevance_score: 1.0 # スコア閾値

scoring:
  title_keyword_weight: 3.0     # タイトルのキーワードマッチ倍率
  abstract_keyword_weight: 1.5  # 要旨のキーワードマッチ倍率
  keyword_rules:
    - keyword: "large language model"
      weight: 5.0
    - keyword: "rag"
      weight: 2.5
  category_rules:
    - category: "cs.CL"
      weight: 2.0
    - category: "cs.LG"
      weight: 1.5

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

### 設定のポイント

- `include_keywords`: 空配列なら全件通過。1つ以上マッチすれば通過。
- `exclude_keywords`: 1つでもマッチすれば除外。
- query ごとに `max_results` や `min_relevance_score` をオーバーライド可能。
- `enabled: false` にしたクエリはスキップされます。

## 📋 CLI コマンド

### 全パイプライン実行

```bash
# 全 enabled クエリを実行
arxiv-watcher run --config config/queries.yaml

# 特定のクエリのみ実行
arxiv-watcher run --config config/queries.yaml --query llm_core

# 要約なしで実行
arxiv-watcher run --config config/queries.yaml --no-summarize

# 詳細ログ
arxiv-watcher run --config config/queries.yaml --verbose
```

### 取得のみ（フィルタ・レポートなし）

```bash
arxiv-watcher fetch --config config/queries.yaml
```

### レポート再生成

```bash
# 最新の run からレポート再生成
arxiv-watcher report

# 特定の run ID を指定
arxiv-watcher report --run-id <RUN_ID>
```

### 要約のみ実行

```bash
arxiv-watcher summarize --run-id <RUN_ID>
```

### バージョン表示

```bash
arxiv-watcher version
```

## 🤖 LLM 日本語要約の有効化

### 1. 環境変数の設定

`.env.example` を `.env` にコピーして設定:

```bash
cp .env.example .env
```

```env
OPENAI_API_KEY=sk-your-api-key-here
OPENAI_BASE_URL=https://api.openai.com/v1  # 省略可
OPENAI_MODEL=gpt-4o-mini
```

### 2. openai パッケージのインストール

```bash
pip install -e ".[llm]"
```

### 要約の条件

以下を**すべて満たす**場合のみ要約が実行されます:
- `config/queries.yaml` の `summarize: true`
- 環境変数 `OPENAI_API_KEY` が設定済み
- 環境変数 `OPENAI_MODEL` が設定済み

条件を満たさない場合は要約がスキップされるだけで、エラーにはなりません。

## 🔄 GitHub Actions

`.github/workflows/daily.yml` が同梱されています。

### 設定方法

1. リポジトリの Settings → Secrets and variables → Actions で以下を設定:
   - `OPENAI_API_KEY` (要約を使う場合)
   - `OPENAI_MODEL` (要約を使う場合)

2. ワークフローは毎日 08:10 JST (23:10 UTC) に自動実行されます。
3. `workflow_dispatch` で手動実行も可能です。
4. 生成されたレポート (`reports/*.md`) が自動的にコミット・プッシュされます。

## 📄 出力例

生成されるレポートの例:

```markdown
# arXiv Daily Digest - 2026-03-29

Generated at: 2026-03-29 08:05 JST
Run ID: a1b2c3d4-...

## Summary
- Queries executed: 2
- New matched papers: 13

## Query: llm_core

### 1. Large Language Models for Reasoning
- arXiv: [2503.12345](https://arxiv.org/abs/2503.12345)
- Score: 25.50
- Match reasons:
  - title matched keyword='large language model' (+15.0)
  - title matched keyword='reasoning' (+6.0)
  - primary_category matched 'cs.CL' (+4.0)

**日本語要約**
本論文は大規模言語モデルの推論能力に関する包括的なサーベイである...
```

## 🧪 テスト

```bash
pip install -e ".[dev]"
pytest
```

## 📁 ディレクトリ構成

```
arxiv-watcher/
├── config/queries.yaml      # 設定ファイル
├── data/arxiv.db             # SQLite DB（自動生成）
├── logs/                     # ログファイル
├── reports/                  # 生成レポート
├── templates/                # Jinja2テンプレート
├── src/arxiv_watcher/        # ソースコード
│   ├── cli.py                # CLIエントリポイント
│   ├── config.py             # 設定読み込み
│   ├── models.py             # データモデル
│   ├── arxiv_client.py       # arXiv APIクライアント
│   ├── parser.py             # Atom XMLパーサー
│   ├── filters.py            # フィルタリング
│   ├── scoring.py            # スコアリング
│   ├── storage.py            # SQLiteストレージ
│   ├── summarizer.py         # LLM要約
│   ├── reporter.py           # レポート生成
│   ├── pipeline.py           # パイプライン統合
│   ├── logging_utils.py      # ロギング
│   └── utils.py              # ユーティリティ
├── tests/                    # テスト
└── .github/workflows/        # GitHub Actions
```

## 🔮 将来の拡張案

- Slack / Discord 通知
- Streamlit Web UI
- PDF 全文解析
- Embedding による意味検索
- 複数ユーザー対応
- メール通知

## 📝 ライセンス

MIT License
