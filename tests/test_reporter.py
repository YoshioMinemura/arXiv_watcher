"""reporter モジュールのテスト"""

import json
from datetime import datetime, timezone
from pathlib import Path

from arxiv_watcher.models import QueryStats
from arxiv_watcher.reporter import generate_report


def test_generate_report_basic(tmp_path):
    """基本的なレポート生成"""
    matches_data = [
        {
            "paper_id_base": "2503.12345",
            "paper_id_full": "2503.12345v2",
            "query_name": "llm_core",
            "title": "Large Language Model Survey",
            "summary": "A survey of LLMs.",
            "authors_json": json.dumps(["Alice", "Bob"]),
            "primary_category": "cs.CL",
            "categories_json": json.dumps(["cs.CL", "cs.AI"]),
            "published_at": "2026-03-28T12:00:00+00:00",
            "updated_at": "2026-03-28T12:00:00+00:00",
            "relevance_score": 15.5,
            "match_reasons_json": json.dumps([
                "title matched keyword='large language model' (+15.0)",
            ]),
            "pdf_url": "https://arxiv.org/pdf/2503.12345v2",
            "abs_url": "https://arxiv.org/abs/2503.12345",
            "llm_summary_ja": None,
            "llm_novelty_ja": None,
            "llm_tags_json": None,
        }
    ]

    query_stats = [
        QueryStats(
            run_id="test-run",
            query_name="llm_core",
            status="completed",
            matched_count=1,
        ),
    ]

    report_path = generate_report(
        run_id="test-run",
        matches_data=matches_data,
        query_stats=query_stats,
        output_dir=tmp_path,
    )

    assert report_path.exists()
    content = report_path.read_text(encoding="utf-8")
    assert "arXiv Daily Digest" in content
    assert "Large Language Model Survey" in content
    assert "test-run" in content
    assert "15.50" in content
    assert "llm_core" in content


def test_generate_report_empty(tmp_path):
    """マッチなしでもレポートが生成される"""
    report_path = generate_report(
        run_id="empty-run",
        matches_data=[],
        query_stats=[
            QueryStats(
                run_id="empty-run",
                query_name="llm_core",
                status="completed",
                matched_count=0,
            ),
        ],
        output_dir=tmp_path,
    )

    assert report_path.exists()
    content = report_path.read_text(encoding="utf-8")
    assert "No matched papers" in content


def test_generate_report_failed_query(tmp_path):
    """失敗したクエリがレポートに表示される"""
    report_path = generate_report(
        run_id="fail-run",
        matches_data=[],
        query_stats=[
            QueryStats(
                run_id="fail-run",
                query_name="broken_query",
                status="failed",
                error_message="API timeout",
            ),
        ],
        output_dir=tmp_path,
    )

    assert report_path.exists()
    content = report_path.read_text(encoding="utf-8")
    assert "failed" in content.lower() or "⚠️" in content


def test_report_respects_top_n(tmp_path):
    """report_top_n による件数制限"""
    matches_data = []
    for i in range(25):
        matches_data.append({
            "paper_id_base": f"2503.{i:05d}",
            "paper_id_full": f"2503.{i:05d}v1",
            "query_name": "test_query",
            "title": f"Paper {i}",
            "summary": f"Summary {i}",
            "authors_json": json.dumps(["Author"]),
            "primary_category": "cs.CL",
            "categories_json": json.dumps(["cs.CL"]),
            "published_at": "2026-03-28T12:00:00+00:00",
            "updated_at": "2026-03-28T12:00:00+00:00",
            "relevance_score": 25 - i,
            "match_reasons_json": json.dumps(["matched"]),
            "pdf_url": None,
            "abs_url": f"https://arxiv.org/abs/2503.{i:05d}",
            "llm_summary_ja": None,
            "llm_novelty_ja": None,
            "llm_tags_json": None,
        })

    report_path = generate_report(
        run_id="topn-run",
        matches_data=matches_data,
        query_stats=[
            QueryStats(
                run_id="topn-run",
                query_name="test_query",
                status="completed",
                matched_count=25,
            ),
        ],
        report_top_n=10,
        output_dir=tmp_path,
    )

    content = report_path.read_text(encoding="utf-8")
    # 最初の10件は表示される
    assert "Paper 0" in content
    # 省略メッセージが表示される
    assert "more papers" in content
