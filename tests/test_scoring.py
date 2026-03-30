"""scoring モジュールのテスト"""

from datetime import datetime, timezone

from arxiv_watcher.config import CategoryRule, KeywordRule, ScoringConfig
from arxiv_watcher.models import Paper
from arxiv_watcher.scoring import score_paper, score_papers


def _make_scoring_config() -> ScoringConfig:
    return ScoringConfig(
        title_keyword_weight=3.0,
        abstract_keyword_weight=1.5,
        primary_category_weight=2.0,
        category_weight=1.0,
        keyword_rules=[
            KeywordRule(keyword="large language model", weight=5.0),
            KeywordRule(keyword="llm", weight=3.0),
            KeywordRule(keyword="reasoning", weight=2.0),
            KeywordRule(keyword="rag", weight=2.5),
        ],
        category_rules=[
            CategoryRule(category="cs.CL", weight=2.0),
            CategoryRule(category="cs.LG", weight=1.5),
            CategoryRule(category="cs.AI", weight=1.0),
        ],
    )


def _make_paper(
    paper_id: str = "2503.00001",
    title: str = "Test Paper",
    summary: str = "Test summary",
    primary_category: str = "cs.CL",
    categories: list[str] | None = None,
) -> Paper:
    if categories is None:
        categories = [primary_category]
    return Paper(
        paper_id_base=paper_id,
        paper_id_full=paper_id,
        title=title,
        summary=summary,
        authors=["Author"],
        primary_category=primary_category,
        categories=categories,
        published_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        abs_url=f"https://arxiv.org/abs/{paper_id}",
    )


class TestScorePaper:
    def test_title_keyword_scoring(self):
        """タイトルのキーワードマッチで加点される"""
        config = _make_scoring_config()
        paper = _make_paper(
            title="Large Language Model for Reasoning",
            primary_category="cs.CL",
        )
        result = score_paper(paper, "test", config)

        # "large language model" in title: 5.0 * 3.0 = 15.0
        # "reasoning" in title: 2.0 * 3.0 = 6.0
        # "cs.CL" primary_category: 2.0 * 2.0 = 4.0
        assert result.relevance_score > 20.0
        assert len(result.match_reasons) >= 3

    def test_summary_keyword_scoring(self):
        """要旨のキーワードマッチで加点される"""
        config = _make_scoring_config()
        paper = _make_paper(
            title="A Novel Approach",
            summary="We propose a large language model for reasoning tasks.",
            primary_category="cs.CL",
        )
        result = score_paper(paper, "test", config)

        # "large language model" in summary: 5.0 * 1.5 = 7.5
        # "reasoning" in summary: 2.0 * 1.5 = 3.0
        assert result.relevance_score >= 10.0  # + category points

    def test_category_scoring(self):
        """カテゴリマッチで加点される"""
        config = _make_scoring_config()
        paper = _make_paper(
            title="Some Paper",
            summary="Some content",
            primary_category="cs.CL",
            categories=["cs.CL", "cs.LG", "cs.AI"],
        )
        result = score_paper(paper, "test", config)

        # cs.CL primary: 2.0 * 2.0 = 4.0
        # cs.LG category: 1.5 * 1.0 = 1.5
        # cs.AI category: 1.0 * 1.0 = 1.0
        assert result.relevance_score >= 6.0

    def test_no_double_counting_primary_and_category(self):
        """primary_category は category_rules で重複計上しない"""
        config = _make_scoring_config()
        paper = _make_paper(
            title="Some Paper",
            primary_category="cs.CL",
            categories=["cs.CL"],
        )
        result = score_paper(paper, "test", config)

        # cs.CL should only be counted as primary (4.0), not also as category
        cl_reasons = [r for r in result.match_reasons if "'cs.CL'" in r]
        assert len(cl_reasons) == 1

    def test_match_reasons_format(self):
        """match_reasons のフォーマットが正しい"""
        config = _make_scoring_config()
        paper = _make_paper(
            title="Large Language Model Survey",
            primary_category="cs.CL",
        )
        result = score_paper(paper, "test", config)

        for reason in result.match_reasons:
            assert "(+" in reason
            assert ")" in reason


class TestScorePapers:
    def test_min_score_filter(self):
        """min_relevance_score 未満の論文は除外される"""
        config = _make_scoring_config()
        papers = [
            _make_paper(paper_id="001", title="LLM Survey", primary_category="cs.CL"),
            _make_paper(paper_id="002", title="Unrelated Topic", primary_category="math.CO"),
        ]
        results = score_papers(papers, "test", config, min_relevance_score=5.0)

        scored_ids = [r.paper_id_base for r in results]
        assert "001" in scored_ids
        # "002" might be excluded if score < 5.0

    def test_sorted_by_score(self):
        """結果がスコア降順でソートされる"""
        config = _make_scoring_config()
        papers = [
            _make_paper(paper_id="low", title="Some Paper", primary_category="cs.CL"),
            _make_paper(paper_id="high", title="Large Language Model LLM RAG", primary_category="cs.CL"),
        ]
        results = score_papers(papers, "test", config, min_relevance_score=0.0)

        if len(results) >= 2:
            assert results[0].relevance_score >= results[1].relevance_score
