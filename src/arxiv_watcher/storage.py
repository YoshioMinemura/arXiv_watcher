"""SQLite ストレージ (§8 準拠)"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from arxiv_watcher.models import MatchResult, Paper, QueryStats, RunContext

logger = logging.getLogger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS papers (
  paper_id_base TEXT PRIMARY KEY,
  paper_id_full TEXT NOT NULL,
  latest_version INTEGER,
  title TEXT NOT NULL,
  summary TEXT NOT NULL,
  authors_json TEXT NOT NULL,
  primary_category TEXT,
  categories_json TEXT NOT NULL,
  published_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  pdf_url TEXT,
  abs_url TEXT NOT NULL,
  doi TEXT,
  comment TEXT,
  journal_ref TEXT,
  raw_entry_json TEXT NOT NULL,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  report_path TEXT,
  error_message TEXT
);

CREATE TABLE IF NOT EXISTS run_queries (
  run_id TEXT NOT NULL,
  query_name TEXT NOT NULL,
  status TEXT NOT NULL,
  fetched_count INTEGER NOT NULL DEFAULT 0,
  parsed_count INTEGER NOT NULL DEFAULT 0,
  inserted_count INTEGER NOT NULL DEFAULT 0,
  matched_count INTEGER NOT NULL DEFAULT 0,
  summarized_count INTEGER NOT NULL DEFAULT 0,
  error_message TEXT,
  PRIMARY KEY (run_id, query_name),
  FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS matches (
  run_id TEXT NOT NULL,
  query_name TEXT NOT NULL,
  paper_id_base TEXT NOT NULL,
  relevance_score REAL NOT NULL,
  match_reasons_json TEXT NOT NULL,
  llm_summary_ja TEXT,
  llm_novelty_ja TEXT,
  llm_tags_json TEXT,
  created_at TEXT NOT NULL,
  PRIMARY KEY (run_id, query_name, paper_id_base),
  FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE,
  FOREIGN KEY (paper_id_base) REFERENCES papers(paper_id_base) ON DELETE CASCADE
);
"""


class Storage:
    """SQLite データベース操作クラス"""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.execute("PRAGMA journal_mode=WAL")
        return self._conn

    def init_db(self) -> None:
        """テーブルを作成する。"""
        self.conn.executescript(_DDL)
        self.conn.commit()
        logger.info("DB 初期化完了: %s", self.db_path)

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # ── papers ──

    def upsert_paper(self, paper: Paper) -> bool:
        """論文を INSERT or UPDATE する。

        Returns:
            True: 新規挿入, False: 更新
        """
        is_new = self._upsert_paper(paper)
        self.conn.commit()
        return is_new

    def _upsert_paper(self, paper: Paper) -> bool:
        now_iso = datetime.now(timezone.utc).isoformat()
        authors_json = json.dumps(paper.authors, ensure_ascii=False)
        categories_json = json.dumps(paper.categories, ensure_ascii=False)
        raw_json = json.dumps(paper.raw_entry_json, ensure_ascii=False, default=str)

        existing = self.conn.execute(
            "SELECT paper_id_base FROM papers WHERE paper_id_base = ?",
            (paper.paper_id_base,),
        ).fetchone()

        if existing:
            # UPDATE
            self.conn.execute(
                """UPDATE papers SET
                    paper_id_full = ?,
                    latest_version = ?,
                    title = ?,
                    summary = ?,
                    authors_json = ?,
                    primary_category = ?,
                    categories_json = ?,
                    published_at = ?,
                    updated_at = ?,
                    pdf_url = ?,
                    abs_url = ?,
                    doi = ?,
                    comment = ?,
                    journal_ref = ?,
                    raw_entry_json = ?,
                    last_seen_at = ?
                WHERE paper_id_base = ?""",
                (
                    paper.paper_id_full,
                    paper.version,
                    paper.title,
                    paper.summary,
                    authors_json,
                    paper.primary_category,
                    categories_json,
                    paper.published_at.isoformat(),
                    paper.updated_at.isoformat(),
                    paper.pdf_url,
                    paper.abs_url,
                    paper.doi,
                    paper.comment,
                    paper.journal_ref,
                    raw_json,
                    now_iso,
                    paper.paper_id_base,
                ),
            )
            return False
        else:
            # INSERT
            self.conn.execute(
                """INSERT INTO papers (
                    paper_id_base, paper_id_full, latest_version,
                    title, summary, authors_json, primary_category, categories_json,
                    published_at, updated_at, pdf_url, abs_url,
                    doi, comment, journal_ref, raw_entry_json,
                    first_seen_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    paper.paper_id_base,
                    paper.paper_id_full,
                    paper.version,
                    paper.title,
                    paper.summary,
                    authors_json,
                    paper.primary_category,
                    categories_json,
                    paper.published_at.isoformat(),
                    paper.updated_at.isoformat(),
                    paper.pdf_url,
                    paper.abs_url,
                    paper.doi,
                    paper.comment,
                    paper.journal_ref,
                    raw_json,
                    now_iso,
                    now_iso,
                ),
            )
            return True

    def upsert_papers(self, papers: list[Paper]) -> int:
        """複数の論文を1トランザクションで UPSERT する。新規挿入件数を返す。"""
        inserted = 0
        try:
            with self.conn:
                for paper in papers:
                    if self._upsert_paper(paper):
                        inserted += 1
        except Exception:
            logger.exception("papers の一括保存に失敗しました。変更をロールバックします")
            raise
        return inserted

    def get_paper(self, paper_id_base: str) -> Paper | None:
        """paper_id_base で論文を取得する。"""
        row = self.conn.execute(
            "SELECT * FROM papers WHERE paper_id_base = ?",
            (paper_id_base,),
        ).fetchone()
        if row is None:
            return None
        return _row_to_paper(row)

    # ── runs ──

    def create_run(self, ctx: RunContext) -> None:
        """実行レコードを作成する。"""
        self.conn.execute(
            """INSERT INTO runs (run_id, started_at, finished_at, status, report_path)
            VALUES (?, ?, ?, ?, ?)""",
            (
                ctx.run_id,
                ctx.started_at.isoformat(),
                ctx.finished_at.isoformat() if ctx.finished_at else None,
                ctx.status,
                ctx.report_path,
            ),
        )
        self.conn.commit()

    def update_run(self, ctx: RunContext, error_message: str | None = None) -> None:
        """実行レコードを更新する。"""
        self.conn.execute(
            """UPDATE runs SET
                finished_at = ?, status = ?, report_path = ?, error_message = ?
            WHERE run_id = ?""",
            (
                ctx.finished_at.isoformat() if ctx.finished_at else None,
                ctx.status,
                ctx.report_path,
                error_message,
                ctx.run_id,
            ),
        )
        self.conn.commit()

    def get_latest_run_id(self) -> str | None:
        """最新の run_id を取得する。"""
        row = self.conn.execute(
            "SELECT run_id FROM runs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        return row["run_id"] if row else None

    # ── run_queries ──

    def save_query_stats(self, stats: QueryStats) -> None:
        """クエリ統計を保存する（INSERT or REPLACE）。"""
        self.conn.execute(
            """INSERT OR REPLACE INTO run_queries
            (run_id, query_name, status, fetched_count, parsed_count,
             inserted_count, matched_count, summarized_count, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                stats.run_id,
                stats.query_name,
                stats.status,
                stats.fetched_count,
                stats.parsed_count,
                stats.inserted_count,
                stats.matched_count,
                stats.summarized_count,
                stats.error_message,
            ),
        )
        self.conn.commit()

    # ── matches ──

    def save_match(self, run_id: str, match: MatchResult) -> None:
        """マッチ結果を保存する。"""
        self._save_match(run_id, match)
        self.conn.commit()

    def _save_match(self, run_id: str, match: MatchResult) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """INSERT OR REPLACE INTO matches
            (run_id, query_name, paper_id_base, relevance_score,
             match_reasons_json, llm_summary_ja, llm_novelty_ja, llm_tags_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id,
                match.query_name,
                match.paper_id_base,
                match.relevance_score,
                json.dumps(match.match_reasons, ensure_ascii=False),
                match.llm_summary_ja,
                match.llm_novelty_ja,
                json.dumps(match.llm_tags, ensure_ascii=False) if match.llm_tags else None,
                now_iso,
            ),
        )

    def save_matches(self, run_id: str, matches: list[MatchResult]) -> None:
        """複数のマッチ結果を1トランザクションで保存する。"""
        with self.conn:
            for match in matches:
                self._save_match(run_id, match)

    def get_matches_for_run(
        self, run_id: str, query_name: str | None = None
    ) -> list[dict]:
        """指定 run のマッチ結果を取得する (papers と JOIN)。"""
        sql = """
            SELECT m.*, p.title, p.summary, p.authors_json, p.primary_category,
                   p.categories_json, p.published_at, p.updated_at,
                   p.pdf_url, p.abs_url, p.doi, p.comment, p.journal_ref,
                   p.paper_id_full
            FROM matches m
            JOIN papers p ON m.paper_id_base = p.paper_id_base
            WHERE m.run_id = ?
        """
        params: list = [run_id]
        if query_name:
            sql += " AND m.query_name = ?"
            params.append(query_name)
        sql += " ORDER BY m.query_name, m.relevance_score DESC, p.published_at DESC"

        rows = self.conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_query_stats_for_run(self, run_id: str) -> list[QueryStats]:
        """指定 run のクエリ統計を取得する。"""
        rows = self.conn.execute(
            "SELECT * FROM run_queries WHERE run_id = ?", (run_id,)
        ).fetchall()
        return [
            QueryStats(
                run_id=row["run_id"],
                query_name=row["query_name"],
                status=row["status"],
                fetched_count=row["fetched_count"],
                parsed_count=row["parsed_count"],
                inserted_count=row["inserted_count"],
                matched_count=row["matched_count"],
                summarized_count=row["summarized_count"],
                error_message=row["error_message"],
            )
            for row in rows
        ]

    def update_match_summary(
        self,
        run_id: str,
        query_name: str,
        paper_id_base: str,
        summary_ja: str | None,
        novelty_ja: str | None,
        tags: list[str] | None,
    ) -> None:
        """要約結果をマッチレコードに更新する。"""
        self.conn.execute(
            """UPDATE matches SET
                llm_summary_ja = ?, llm_novelty_ja = ?, llm_tags_json = ?
            WHERE run_id = ? AND query_name = ? AND paper_id_base = ?""",
            (
                summary_ja,
                novelty_ja,
                json.dumps(tags, ensure_ascii=False) if tags else None,
                run_id,
                query_name,
                paper_id_base,
            ),
        )
        self.conn.commit()


def _row_to_paper(row: sqlite3.Row) -> Paper:
    """DB行をPaperに変換する。"""
    from datetime import datetime

    return Paper(
        paper_id_base=row["paper_id_base"],
        paper_id_full=row["paper_id_full"],
        version=row["latest_version"],
        title=row["title"],
        summary=row["summary"],
        authors=json.loads(row["authors_json"]),
        primary_category=row["primary_category"],
        categories=json.loads(row["categories_json"]),
        published_at=datetime.fromisoformat(row["published_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        pdf_url=row["pdf_url"],
        abs_url=row["abs_url"],
        doi=row["doi"],
        comment=row["comment"],
        journal_ref=row["journal_ref"],
        raw_entry_json=json.loads(row["raw_entry_json"]),
    )
