"""storage モジュールのテスト"""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from arxiv_watcher.models import MatchResult, Paper, QueryStats, RunContext
from arxiv_watcher.storage import Storage


@pytest.fixture
def storage(tmp_path):
    """テスト用の一時 Storage を作成する。"""
    db_path = tmp_path / "test.db"
    s = Storage(db_path)
    s.init_db()
    yield s
    s.close()


def _make_paper(paper_id: str = "2503.00001", title: str = "Test Paper") -> Paper:
    return Paper(
        paper_id_base=paper_id,
        paper_id_full=f"{paper_id}v1",
        version=1,
        title=title,
        summary="Test summary",
        authors=["Alice", "Bob"],
        primary_category="cs.CL",
        categories=["cs.CL", "cs.AI"],
        published_at=datetime(2026, 3, 28, 12, 0, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 3, 28, 12, 0, 0, tzinfo=timezone.utc),
        pdf_url="https://arxiv.org/pdf/2503.00001v1",
        abs_url="https://arxiv.org/abs/2503.00001",
        raw_entry_json={"id": "test"},
    )


class TestPaperUpsert:
    def test_initial_insert(self, storage):
        """初回 INSERT が成功する"""
        paper = _make_paper()
        is_new = storage.upsert_paper(paper)
        assert is_new is True

        retrieved = storage.get_paper("2503.00001")
        assert retrieved is not None
        assert retrieved.title == "Test Paper"
        assert retrieved.authors == ["Alice", "Bob"]

    def test_duplicate_upsert(self, storage):
        """同じ paper_id_base で2回目は UPDATE になる"""
        paper1 = _make_paper()
        storage.upsert_paper(paper1)

        paper2 = _make_paper(title="Updated Title")
        is_new = storage.upsert_paper(paper2)
        assert is_new is False

        retrieved = storage.get_paper("2503.00001")
        assert retrieved.title == "Updated Title"

    def test_version_update(self, storage):
        """バージョンが更新される"""
        paper_v1 = _make_paper()
        storage.upsert_paper(paper_v1)

        paper_v2 = Paper(
            paper_id_base="2503.00001",
            paper_id_full="2503.00001v2",
            version=2,
            title="Updated Paper v2",
            summary="Updated summary",
            authors=["Alice", "Bob", "Carol"],
            primary_category="cs.CL",
            categories=["cs.CL", "cs.AI"],
            published_at=datetime(2026, 3, 28, 12, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 3, 29, 12, 0, 0, tzinfo=timezone.utc),
            abs_url="https://arxiv.org/abs/2503.00001",
            raw_entry_json={"id": "test_v2"},
        )
        storage.upsert_paper(paper_v2)

        retrieved = storage.get_paper("2503.00001")
        assert retrieved.version == 2
        assert retrieved.paper_id_full == "2503.00001v2"
        assert len(retrieved.authors) == 3

    def test_first_seen_at_preserved(self, storage):
        """first_seen_at は初回 INSERT 時のみ設定される"""
        paper = _make_paper()
        storage.upsert_paper(paper)

        # first_seen_at を直接確認
        row1 = storage.conn.execute(
            "SELECT first_seen_at, last_seen_at FROM papers WHERE paper_id_base = ?",
            ("2503.00001",),
        ).fetchone()
        first_seen_1 = row1["first_seen_at"]

        # UPDATE
        paper2 = _make_paper(title="Updated")
        storage.upsert_paper(paper2)

        row2 = storage.conn.execute(
            "SELECT first_seen_at, last_seen_at FROM papers WHERE paper_id_base = ?",
            ("2503.00001",),
        ).fetchone()

        assert row2["first_seen_at"] == first_seen_1  # 変わらない
        assert row2["last_seen_at"] != first_seen_1   # 更新される


class TestRunsAndMatches:
    def test_create_and_update_run(self, storage):
        """run の作成と更新"""
        ctx = RunContext(
            run_id="test-run-1",
            started_at=datetime.now(timezone.utc),
            status="running",
        )
        storage.create_run(ctx)

        ctx.status = "completed"
        ctx.finished_at = datetime.now(timezone.utc)
        ctx.report_path = "reports/2026-03-28.md"
        storage.update_run(ctx)

        latest = storage.get_latest_run_id()
        assert latest == "test-run-1"

    def test_save_and_get_matches(self, storage):
        """マッチ結果の保存と取得"""
        # paper を先に保存
        storage.upsert_paper(_make_paper())

        # run を作成
        ctx = RunContext(
            run_id="test-run-1",
            started_at=datetime.now(timezone.utc),
            status="running",
        )
        storage.create_run(ctx)

        # match を保存
        match = MatchResult(
            paper_id_base="2503.00001",
            query_name="test_query",
            matched=True,
            relevance_score=15.5,
            match_reasons=["title matched keyword='llm' (+9.0)"],
        )
        storage.save_match("test-run-1", match)

        # 取得
        results = storage.get_matches_for_run("test-run-1")
        assert len(results) == 1
        assert results[0]["relevance_score"] == 15.5
        assert results[0]["title"] == "Test Paper"

    def test_query_stats(self, storage):
        """クエリ統計の保存と取得"""
        ctx = RunContext(
            run_id="test-run-1",
            started_at=datetime.now(timezone.utc),
            status="running",
        )
        storage.create_run(ctx)

        stats = QueryStats(
            run_id="test-run-1",
            query_name="llm_core",
            status="completed",
            fetched_count=1,
            parsed_count=50,
            inserted_count=45,
            matched_count=12,
        )
        storage.save_query_stats(stats)

        retrieved = storage.get_query_stats_for_run("test-run-1")
        assert len(retrieved) == 1
        assert retrieved[0].matched_count == 12
