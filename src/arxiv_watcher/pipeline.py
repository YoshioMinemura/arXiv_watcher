"""パイプライン (§16 準拠)"""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path

from arxiv_watcher.arxiv_client import fetch_arxiv
from arxiv_watcher.config import AppConfig, QueryConfig
from arxiv_watcher.filters import filter_by_keywords, filter_by_lookback
from arxiv_watcher.models import QueryStats, RunContext
from arxiv_watcher.parser import parse_feed
from arxiv_watcher.reporter import generate_report
from arxiv_watcher.scoring import score_papers
from arxiv_watcher.storage import Storage
from arxiv_watcher.summarizer import is_summarization_available, summarize_paper
from arxiv_watcher.utils import now_utc

logger = logging.getLogger(__name__)


def run_pipeline(
    config: AppConfig,
    storage: Storage,
    *,
    query_name: str | None = None,
    no_summarize: bool = False,
    report_output_dir: Path | None = None,
    template_dir: Path | None = None,
) -> RunContext:
    """fetch → filter → score → save → summarize → report のパイプラインを実行する。

    Args:
        config: アプリケーション設定
        storage: ストレージ
        query_name: 特定 query のみ実行する場合
        no_summarize: 要約をスキップする場合 True
        report_output_dir: レポート出力先
        template_dir: テンプレートディレクトリ

    Returns:
        RunContext
    """
    run_id = str(uuid.uuid4())
    ctx = RunContext(run_id=run_id, started_at=now_utc(), status="running")
    storage.create_run(ctx)
    logger.info("パイプライン開始: run_id=%s", run_id)

    # 対象 query を決定
    queries = config.get_enabled_queries()
    if query_name:
        queries = [q for q in queries if q.name == query_name]
        if not queries:
            logger.error("Query '%s' が見つかりません", query_name)
            ctx.status = "failed"
            ctx.finished_at = now_utc()
            storage.update_run(ctx, error_message=f"Query '{query_name}' not found")
            return ctx

    success_count = 0
    total_matched = 0

    for i, query in enumerate(queries):
        if i > 0:
            delay = config.defaults.request_delay_seconds
            logger.debug("リクエスト間隔: %.1f秒待機", delay)
            time.sleep(delay)

        try:
            matched = _process_query(
                config=config,
                storage=storage,
                query=query,
                run_id=run_id,
                no_summarize=no_summarize,
            )
            total_matched += matched
            success_count += 1
        except Exception as e:
            logger.error("Query '%s' の処理に失敗しました: %s", query.name, e, exc_info=True)
            stats = QueryStats(
                run_id=run_id,
                query_name=query.name,
                status="failed",
                error_message=str(e),
            )
            storage.save_query_stats(stats)

    # レポート生成
    if success_count > 0:
        try:
            matches_data = storage.get_matches_for_run(run_id)
            query_stats_list = storage.get_query_stats_for_run(run_id)

            report_path = generate_report(
                run_id=run_id,
                matches_data=matches_data,
                query_stats=query_stats_list,
                tz_name=config.defaults.timezone,
                report_top_n=config.defaults.report_top_n,
                output_dir=report_output_dir,
                template_dir=template_dir,
            )
            ctx.report_path = str(report_path)
            ctx.status = "completed"
            logger.info("パイプライン完了: report=%s, matched=%d papers", report_path, total_matched)
        except Exception as e:
            logger.error("レポート生成に失敗しました: %s", e, exc_info=True)
            ctx.status = "failed"
            ctx.finished_at = now_utc()
            storage.update_run(ctx, error_message=f"Report generation failed: {e}")
            return ctx
    else:
        ctx.status = "failed"
        logger.error("全 query が失敗しました")

    ctx.finished_at = now_utc()
    storage.update_run(ctx)
    return ctx


def _process_query(
    *,
    config: AppConfig,
    storage: Storage,
    query: QueryConfig,
    run_id: str,
    no_summarize: bool,
) -> int:
    """個別 query を処理する。

    Returns:
        マッチ件数
    """
    logger.info("Query '%s' 処理開始", query.name)
    stats = QueryStats(run_id=run_id, query_name=query.name, status="running")

    # 1. Fetch
    max_results = config.resolve_max_results(query)
    xml_text = fetch_arxiv(
        search_query=query.search_query,
        start=config.defaults.start,
        max_results=max_results,
        sort_by=config.defaults.sort_by,
        sort_order=config.defaults.sort_order,
        user_agent=config.defaults.user_agent,
    )
    # feedparser がパースする前にバイト数で概算
    stats.fetched_count = 1  # API呼び出し回数

    # 2. Parse
    papers = parse_feed(xml_text)
    stats.parsed_count = len(papers)
    logger.info("Query '%s': %d papers parsed", query.name, len(papers))

    # 3. Lookback filter
    papers = filter_by_lookback(
        papers,
        lookback_days=config.defaults.lookback_days,
        tz_name=config.defaults.timezone,
    )

    # 4. Keyword filter
    papers = filter_by_keywords(
        papers,
        include_keywords=query.include_keywords,
        exclude_keywords=query.exclude_keywords,
    )

    # 5. Score
    min_score = config.resolve_min_relevance_score(query)
    matches = score_papers(
        papers,
        query_name=query.name,
        scoring=config.scoring,
        min_relevance_score=min_score,
    )
    stats.matched_count = len(matches)

    # 6. Papers UPSERT
    inserted = storage.upsert_papers(papers)
    stats.inserted_count = inserted

    # 7. Matches INSERT
    storage.save_matches(run_id, matches)

    # 8. 要約（optional）
    if not no_summarize and is_summarization_available(config.defaults.summarize):
        summarized = 0
        for match in matches:
            paper = storage.get_paper(match.paper_id_base)
            if paper:
                from arxiv_watcher.summarizer import summarize_paper as do_summarize

                result = do_summarize(
                    title=paper.title,
                    summary=paper.summary,
                    primary_category=paper.primary_category,
                    categories=paper.categories,
                )
                if result.ja_summary:
                    storage.update_match_summary(
                        run_id=run_id,
                        query_name=query.name,
                        paper_id_base=match.paper_id_base,
                        summary_ja=result.ja_summary,
                        novelty_ja=result.novelty,
                        tags=result.tags,
                    )
                    summarized += 1
        stats.summarized_count = summarized
        logger.info("Query '%s': %d papers summarized", query.name, summarized)

    # 9. Stats 更新
    stats.status = "completed"
    storage.save_query_stats(stats)
    logger.info(
        "Query '%s' 完了: parsed=%d, inserted=%d, matched=%d",
        query.name,
        stats.parsed_count,
        stats.inserted_count,
        stats.matched_count,
    )

    return stats.matched_count


def fetch_only(
    config: AppConfig,
    storage: Storage,
    *,
    query_name: str | None = None,
) -> RunContext:
    """fetch + parse + DB保存のみ実行する（フィルタ・スコア・レポートは行わない）。"""
    run_id = str(uuid.uuid4())
    ctx = RunContext(run_id=run_id, started_at=now_utc(), status="running")
    storage.create_run(ctx)
    logger.info("Fetch 開始: run_id=%s", run_id)

    queries = config.get_enabled_queries()
    if query_name:
        queries = [q for q in queries if q.name == query_name]

    success_count = 0

    for i, query in enumerate(queries):
        if i > 0:
            time.sleep(config.defaults.request_delay_seconds)

        try:
            max_results = config.resolve_max_results(query)
            xml_text = fetch_arxiv(
                search_query=query.search_query,
                start=config.defaults.start,
                max_results=max_results,
                sort_by=config.defaults.sort_by,
                sort_order=config.defaults.sort_order,
                user_agent=config.defaults.user_agent,
            )
            papers = parse_feed(xml_text)
            inserted = storage.upsert_papers(papers)

            stats = QueryStats(
                run_id=run_id,
                query_name=query.name,
                status="completed",
                fetched_count=1,
                parsed_count=len(papers),
                inserted_count=inserted,
            )
            storage.save_query_stats(stats)
            success_count += 1
            logger.info(
                "Fetch query '%s' 完了: parsed=%d, inserted=%d",
                query.name,
                len(papers),
                inserted,
            )
        except Exception as e:
            logger.error("Fetch query '%s' 失敗: %s", query.name, e, exc_info=True)
            stats = QueryStats(
                run_id=run_id,
                query_name=query.name,
                status="failed",
                error_message=str(e),
            )
            storage.save_query_stats(stats)

    ctx.status = "completed" if success_count > 0 else "failed"
    ctx.finished_at = now_utc()
    storage.update_run(ctx)
    return ctx
