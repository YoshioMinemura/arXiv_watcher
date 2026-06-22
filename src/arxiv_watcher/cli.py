"""CLI エントリポイント (§15 準拠)"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv

from arxiv_watcher import __version__

app = typer.Typer(
    name="arxiv-watcher",
    help="arXiv新着論文ウォッチャー - 関心分野の論文を自動収集・フィルタ・日本語要約",
    add_completion=False,
)


def _get_project_root() -> Path:
    """プロジェクトルートを推定する。"""
    return Path.cwd()


@app.command()
def init(
    project_dir: Optional[str] = typer.Option(None, help="プロジェクトディレクトリ"),
) -> None:
    """プロジェクトを初期化する（ディレクトリ作成、DB初期化、サンプル設定生成）。"""
    from arxiv_watcher.logging_utils import setup_logging
    from arxiv_watcher.storage import Storage

    root = Path(project_dir) if project_dir else _get_project_root()
    setup_logging(log_dir=root / "logs")

    # ディレクトリ作成
    for d in ["config", "data", "logs", "reports", "templates"]:
        (root / d).mkdir(parents=True, exist_ok=True)

    # DB 初期化
    db_path = root / "data" / "arxiv.db"
    storage = Storage(db_path)
    storage.init_db()
    storage.close()

    # サンプル queries.yaml（既存なら上書きしない）
    config_path = root / "config" / "queries.yaml"
    if not config_path.exists():
        _write_sample_config(config_path)
        typer.echo(f"サンプル設定ファイルを作成しました: {config_path}")
    else:
        typer.echo(f"設定ファイルは既に存在します: {config_path}")

    typer.echo(f"初期化完了: {root}")


@app.command()
def fetch(
    config: str = typer.Option("config/queries.yaml", "--config", "-c", help="設定ファイルパス"),
    query: Optional[str] = typer.Option(None, "--query", "-q", help="特定のqueryのみ実行"),
    all_queries: bool = typer.Option(False, "--all", help="全query実行（enabledに関わらず）"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="詳細ログ出力"),
) -> None:
    """arXiv APIから論文を取得してDBに保存する（レポート生成なし）。"""
    load_dotenv()

    from arxiv_watcher.config import load_config
    from arxiv_watcher.logging_utils import setup_logging
    from arxiv_watcher.pipeline import fetch_only
    from arxiv_watcher.storage import Storage

    setup_logging(verbose=verbose)
    cfg = load_config(Path(config))
    storage = Storage(Path("data/arxiv.db"))
    storage.init_db()

    try:
        ctx = fetch_only(cfg, storage, query_name=query, include_disabled=all_queries)
        typer.echo(f"Fetch 完了: run_id={ctx.run_id}, status={ctx.status}")
        if ctx.status == "failed":
            raise typer.Exit(code=1)
    finally:
        storage.close()


@app.command()
def run(
    config: str = typer.Option("config/queries.yaml", "--config", "-c", help="設定ファイルパス"),
    query: Optional[str] = typer.Option(None, "--query", "-q", help="特定のqueryのみ実行"),
    all_queries: bool = typer.Option(False, "--all", help="全query実行"),
    no_summarize: bool = typer.Option(False, "--no-summarize", help="要約をスキップ"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="詳細ログ出力"),
) -> None:
    """fetch → filter → score → save → summarize → report を一括実行する。"""
    load_dotenv()

    from arxiv_watcher.config import load_config
    from arxiv_watcher.logging_utils import setup_logging
    from arxiv_watcher.pipeline import run_pipeline
    from arxiv_watcher.storage import Storage

    setup_logging(verbose=verbose)
    cfg = load_config(Path(config))
    storage = Storage(Path("data/arxiv.db"))
    storage.init_db()

    try:
        ctx = run_pipeline(
            cfg,
            storage,
            query_name=query,
            include_disabled=all_queries,
            no_summarize=no_summarize,
            template_dir=Path("templates"),
        )

        if ctx.report_path:
            typer.echo(f"レポート: {ctx.report_path}")
        typer.echo(f"Run 完了: run_id={ctx.run_id}, status={ctx.status}")

        if ctx.status == "failed":
            raise typer.Exit(code=1)
    finally:
        storage.close()


@app.command()
def report(
    run_id: Optional[str] = typer.Option(None, "--run-id", "-r", help="対象の run ID"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="出力ディレクトリ"),
    config: str = typer.Option("config/queries.yaml", "--config", "-c", help="設定ファイルパス"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="詳細ログ出力"),
) -> None:
    """指定 run からレポートを再生成する。"""
    load_dotenv()

    from arxiv_watcher.config import load_config
    from arxiv_watcher.logging_utils import setup_logging
    from arxiv_watcher.reporter import generate_report
    from arxiv_watcher.storage import Storage

    setup_logging(verbose=verbose)
    cfg = load_config(Path(config))
    storage = Storage(Path("data/arxiv.db"))
    storage.init_db()

    try:
        target_run_id = run_id or storage.get_latest_run_id()
        if not target_run_id:
            typer.echo("実行履歴が見つかりません。先に `run` を実行してください。")
            raise typer.Exit(code=1)

        matches_data = storage.get_matches_for_run(target_run_id)
        query_stats_list = storage.get_query_stats_for_run(target_run_id)

        output_dir = Path(output) if output else None
        report_path = generate_report(
            run_id=target_run_id,
            matches_data=matches_data,
            query_stats=query_stats_list,
            tz_name=cfg.defaults.timezone,
            report_top_n=cfg.defaults.report_top_n,
            output_dir=output_dir,
            template_dir=Path("templates"),
        )
        typer.echo(f"レポート生成完了: {report_path}")
    finally:
        storage.close()


@app.command()
def summarize(
    run_id: Optional[str] = typer.Option(None, "--run-id", "-r", help="対象の run ID"),
    config: str = typer.Option("config/queries.yaml", "--config", "-c", help="設定ファイルパス"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="詳細ログ出力"),
) -> None:
    """最新 run または指定 run の matches に対して要約を生成する。"""
    load_dotenv()

    from arxiv_watcher.config import load_config
    from arxiv_watcher.logging_utils import setup_logging
    from arxiv_watcher.storage import Storage
    from arxiv_watcher.summarizer import is_summarization_available, summarize_paper

    setup_logging(verbose=verbose)
    cfg = load_config(Path(config))

    if not is_summarization_available(cfg.defaults.summarize):
        typer.echo("要約が有効化されていません。OpenAI または local LLM の環境変数を設定してください。")
        raise typer.Exit(code=1)

    storage = Storage(Path("data/arxiv.db"))
    storage.init_db()

    try:
        target_run_id = run_id or storage.get_latest_run_id()
        if not target_run_id:
            typer.echo("実行履歴が見つかりません。先に `run` を実行してください。")
            raise typer.Exit(code=1)

        matches_data = storage.get_matches_for_run(target_run_id)
        summarized = 0

        for m in matches_data:
            if m.get("llm_summary_ja"):
                continue  # 既に要約済み

            result = summarize_paper(
                title=m["title"],
                summary=m["summary"],
                primary_category=m.get("primary_category"),
                categories=_decode_categories(m.get("categories_json")),
            )

            if result.ja_summary:
                storage.update_match_summary(
                    run_id=target_run_id,
                    query_name=m["query_name"],
                    paper_id_base=m["paper_id_base"],
                    summary_ja=result.ja_summary,
                    novelty_ja=result.novelty,
                    tags=result.tags,
                )
                summarized += 1

        typer.echo(f"要約完了: {summarized} papers summarized")
    finally:
        storage.close()


@app.command()
def version() -> None:
    """バージョンを表示する。"""
    typer.echo(f"arxiv-watcher {__version__}")


def _decode_categories(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return []
        if isinstance(decoded, list):
            return [str(item) for item in decoded]
    return []


def _write_sample_config(path: Path) -> None:
    """サンプル設定ファイルを書き出す。"""
    sample = """\
defaults:
  max_results: 50
  start: 0
  sort_by: submittedDate
  sort_order: descending
  request_delay_seconds: 3.1
  lookback_days: 2
  timezone: Asia/Tokyo
  report_top_n: 20
  user_agent: "arxiv-watcher/0.1 (contact: your_email@example.com)"
  summarize: true
  min_relevance_score: 1.0

scoring:
  title_keyword_weight: 3.0
  abstract_keyword_weight: 1.5
  primary_category_weight: 2.0
  category_weight: 1.0
  keyword_rules:
    - keyword: "large language model"
      weight: 5.0
    - keyword: "llm"
      weight: 3.0
    - keyword: "reasoning"
      weight: 2.0
    - keyword: "alignment"
      weight: 2.0
  category_rules:
    - category: "cs.CL"
      weight: 2.0
    - category: "cs.LG"
      weight: 1.5
    - category: "cs.AI"
      weight: 1.0

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
"""
    path.write_text(sample, encoding="utf-8")


if __name__ == "__main__":
    app()
