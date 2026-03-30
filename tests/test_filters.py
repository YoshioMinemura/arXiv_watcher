"""filters モジュールのテスト"""

from datetime import datetime, timezone, timedelta

from arxiv_watcher.filters import filter_by_keywords, filter_by_lookback
from arxiv_watcher.models import Paper


def _make_paper(
    paper_id: str = "2503.00001",
    title: str = "Test Paper",
    summary: str = "Test summary",
    categories: list[str] | None = None,
    primary_category: str = "cs.CL",
    published_at: datetime | None = None,
) -> Paper:
    if published_at is None:
        published_at = datetime.now(timezone.utc)
    if categories is None:
        categories = ["cs.CL"]
    return Paper(
        paper_id_base=paper_id,
        paper_id_full=paper_id,
        title=title,
        summary=summary,
        authors=["Author"],
        primary_category=primary_category,
        categories=categories,
        published_at=published_at,
        updated_at=published_at,
        abs_url=f"https://arxiv.org/abs/{paper_id}",
    )


class TestFilterByKeywords:
    def test_include_empty_passes_all(self):
        """include_keywords が空なら全て通す"""
        papers = [_make_paper(title="Any title")]
        result = filter_by_keywords(papers, include_keywords=[], exclude_keywords=[])
        assert len(result) == 1

    def test_include_matches(self):
        """include keyword が含まれていれば通す"""
        papers = [
            _make_paper(paper_id="001", title="Large Language Model Survey"),
            _make_paper(paper_id="002", title="Computer Vision Methods"),
        ]
        result = filter_by_keywords(
            papers, include_keywords=["large language model"], exclude_keywords=[]
        )
        assert len(result) == 1
        assert result[0].paper_id_base == "001"

    def test_exclude_removes(self):
        """exclude keyword が含まれていれば除外"""
        papers = [
            _make_paper(paper_id="001", title="LLM for Protein Analysis"),
            _make_paper(paper_id="002", title="LLM for Text Generation"),
        ]
        result = filter_by_keywords(
            papers,
            include_keywords=["llm"],
            exclude_keywords=["protein"],
        )
        assert len(result) == 1
        assert result[0].paper_id_base == "002"

    def test_exclude_takes_priority(self):
        """exclude は include より優先される"""
        papers = [
            _make_paper(
                paper_id="001",
                title="LLM for Protein Structure",
                summary="Large language model applied to protein folding"
            ),
        ]
        result = filter_by_keywords(
            papers,
            include_keywords=["llm"],
            exclude_keywords=["protein"],
        )
        assert len(result) == 0

    def test_case_insensitive(self):
        """大文字小文字を区別しない"""
        papers = [_make_paper(title="LARGE LANGUAGE MODEL")]
        result = filter_by_keywords(
            papers, include_keywords=["large language model"], exclude_keywords=[]
        )
        assert len(result) == 1

    def test_summary_matching(self):
        """summary にキーワードが含まれる場合"""
        papers = [_make_paper(summary="This paper studies retrieval augmented generation.")]
        result = filter_by_keywords(
            papers, include_keywords=["retrieval augmented generation"], exclude_keywords=[]
        )
        assert len(result) == 1


class TestFilterByLookback:
    def test_within_lookback(self):
        """lookback_days 以内の論文は通す"""
        recent = datetime.now(timezone.utc) - timedelta(hours=12)
        papers = [_make_paper(published_at=recent)]
        result = filter_by_lookback(papers, lookback_days=2)
        assert len(result) == 1

    def test_beyond_lookback(self):
        """lookback_days を超えた論文は除外"""
        old = datetime.now(timezone.utc) - timedelta(days=10)
        papers = [_make_paper(published_at=old)]
        result = filter_by_lookback(papers, lookback_days=2)
        assert len(result) == 0

    def test_mixed(self):
        """混在した論文の正しいフィルタリング"""
        recent = datetime.now(timezone.utc) - timedelta(hours=6)
        old = datetime.now(timezone.utc) - timedelta(days=10)
        papers = [
            _make_paper(paper_id="001", published_at=recent),
            _make_paper(paper_id="002", published_at=old),
        ]
        result = filter_by_lookback(papers, lookback_days=2)
        assert len(result) == 1
        assert result[0].paper_id_base == "001"
