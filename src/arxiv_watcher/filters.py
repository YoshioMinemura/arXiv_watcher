"""フィルタリング (§11 準拠)"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from arxiv_watcher.models import Paper
from arxiv_watcher.utils import get_timezone

logger = logging.getLogger(__name__)


def filter_by_lookback(
    papers: list[Paper],
    lookback_days: int,
    tz_name: str = "Asia/Tokyo",
) -> list[Paper]:
    """lookback_days 以内に投稿された論文を返す。

    基準日は tz_name のローカル日付。
    """
    tz = get_timezone(tz_name)
    local_now = datetime.now(tz)
    cutoff_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(
        days=lookback_days
    )
    cutoff_utc = cutoff_local.astimezone(timezone.utc)

    result = []
    for paper in papers:
        pub = paper.published_at
        if pub.tzinfo is None:
            pub = pub.replace(tzinfo=timezone.utc)
        if pub >= cutoff_utc:
            result.append(paper)

    logger.info(
        "lookback フィルタ: %d / %d papers (lookback_days=%d, cutoff=%s)",
        len(result),
        len(papers),
        lookback_days,
        cutoff_utc.isoformat(),
    )
    return result


def filter_by_keywords(
    papers: list[Paper],
    include_keywords: list[str],
    exclude_keywords: list[str],
) -> list[Paper]:
    """include/exclude キーワードでフィルタする。

    - include_keywords が空なら全て通す
    - include_keywords が空でなければ、1つ以上含まれていれば通す
    - exclude_keywords は1つでも含まれていたら除外
    """
    result = []
    for paper in papers:
        text = _build_filter_text(paper)

        # exclude チェック
        if _any_keyword_in_text(exclude_keywords, text):
            continue

        # include チェック
        if include_keywords and not _any_keyword_in_text(include_keywords, text):
            continue

        result.append(paper)

    logger.info(
        "keyword フィルタ: %d / %d papers (include=%d, exclude=%d keywords)",
        len(result),
        len(papers),
        len(include_keywords),
        len(exclude_keywords),
    )
    return result


def _build_filter_text(paper: Paper) -> str:
    """フィルタ対象テキストを構築する（小文字化）。"""
    parts = [
        paper.title,
        paper.summary,
        paper.primary_category or "",
        " ".join(paper.categories),
    ]
    return " ".join(parts).lower()


def _any_keyword_in_text(keywords: list[str], text: str) -> bool:
    """キーワードのいずれかがテキストに含まれるか。"""
    return any(kw.lower() in text for kw in keywords)
