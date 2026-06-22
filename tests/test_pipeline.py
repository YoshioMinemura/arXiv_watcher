"""pipeline モジュールのテスト"""

from datetime import datetime, timezone

from arxiv_watcher.config import AppConfig, QueryConfig
from arxiv_watcher.models import Paper
from arxiv_watcher.pipeline import fetch_only
from arxiv_watcher.storage import Storage


def _paper() -> Paper:
    return Paper(
        paper_id_base="2503.00001",
        paper_id_full="2503.00001v1",
        version=1,
        title="Test Paper",
        summary="Test summary",
        authors=["Author"],
        primary_category="cs.CL",
        categories=["cs.CL"],
        published_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        abs_url="https://arxiv.org/abs/2503.00001",
    )


def test_fetch_only_all_includes_disabled_queries(tmp_path, monkeypatch):
    config = AppConfig(
        queries=[
            QueryConfig(
                name="disabled_query",
                enabled=False,
                search_query="cat:cs.CL",
            )
        ]
    )
    storage = Storage(tmp_path / "test.db")
    storage.init_db()

    monkeypatch.setattr("arxiv_watcher.pipeline.fetch_arxiv", lambda **kwargs: "<feed />")
    monkeypatch.setattr("arxiv_watcher.pipeline.parse_feed", lambda xml_text: [_paper()])

    try:
        skipped = fetch_only(config, storage)
        assert skipped.status == "failed"

        included = fetch_only(config, storage, include_disabled=True)
        assert included.status == "completed"
        stats = storage.get_query_stats_for_run(included.run_id)
        assert stats[0].query_name == "disabled_query"
    finally:
        storage.close()
