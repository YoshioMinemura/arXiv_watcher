"""スコアリング (§12 準拠)"""

from __future__ import annotations

import logging

from arxiv_watcher.config import ScoringConfig
from arxiv_watcher.models import MatchResult, Paper

logger = logging.getLogger(__name__)


def score_paper(
    paper: Paper,
    query_name: str,
    scoring: ScoringConfig,
) -> MatchResult:
    """論文の関連度スコアを計算する。

    Args:
        paper: 対象論文
        query_name: クエリ名
        scoring: スコアリング設定

    Returns:
        MatchResult（スコアとマッチ理由を含む）
    """
    total_score = 0.0
    reasons: list[str] = []

    title_lower = paper.title.lower()
    summary_lower = paper.summary.lower()

    # A. keyword_rules
    for rule in scoring.keyword_rules:
        kw = rule.keyword.lower()

        # タイトルにキーワードが含まれる
        if kw in title_lower:
            points = rule.weight * scoring.title_keyword_weight
            total_score += points
            reasons.append(
                f"title matched keyword='{rule.keyword}' (+{points:.1f})"
            )

        # 要旨にキーワードが含まれる
        if kw in summary_lower:
            points = rule.weight * scoring.abstract_keyword_weight
            total_score += points
            reasons.append(
                f"summary matched keyword='{rule.keyword}' (+{points:.1f})"
            )

    # B. category_rules
    for rule in scoring.category_rules:
        cat = rule.category

        # primary_category が一致
        if paper.primary_category and paper.primary_category == cat:
            points = rule.weight * scoring.primary_category_weight
            total_score += points
            reasons.append(
                f"primary_category matched '{cat}' (+{points:.1f})"
            )

        # categories のどれかに一致（primary_category と重複計上しない）
        elif cat in paper.categories:
            points = rule.weight * scoring.category_weight
            total_score += points
            reasons.append(
                f"category matched '{cat}' (+{points:.1f})"
            )

    return MatchResult(
        paper_id_base=paper.paper_id_base,
        query_name=query_name,
        matched=True,
        relevance_score=total_score,
        match_reasons=reasons,
    )


def score_papers(
    papers: list[Paper],
    query_name: str,
    scoring: ScoringConfig,
    min_relevance_score: float = 0.0,
) -> list[MatchResult]:
    """複数の論文をスコアリングし、min_relevance_score 以上のものを返す。"""
    results = []
    for paper in papers:
        match = score_paper(paper, query_name, scoring)
        if match.relevance_score >= min_relevance_score:
            results.append(match)

    # スコア降順でソート
    results.sort(key=lambda m: m.relevance_score, reverse=True)

    logger.info(
        "スコアリング完了 (query=%s): %d / %d papers がスコア閾値 (%.1f) 以上",
        query_name,
        len(results),
        len(papers),
        min_relevance_score,
    )
    return results
