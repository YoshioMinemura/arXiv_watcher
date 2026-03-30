"""データモデル定義 (§7.2 準拠)"""

from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


class Paper(BaseModel):
    """arXiv論文のメタデータ"""

    paper_id_base: str
    paper_id_full: str
    version: int | None = None
    title: str
    summary: str
    authors: list[str] = Field(default_factory=list)
    primary_category: str | None = None
    categories: list[str] = Field(default_factory=list)
    published_at: datetime
    updated_at: datetime
    pdf_url: str | None = None
    abs_url: str
    doi: str | None = None
    comment: str | None = None
    journal_ref: str | None = None
    raw_entry_json: dict = Field(default_factory=dict)


class MatchResult(BaseModel):
    """フィルタ・スコアリング結果"""

    paper_id_base: str
    query_name: str
    matched: bool = False
    relevance_score: float = 0.0
    match_reasons: list[str] = Field(default_factory=list)
    llm_summary_ja: str | None = None
    llm_novelty_ja: str | None = None
    llm_tags: list[str] | None = None


class RunContext(BaseModel):
    """実行コンテキスト"""

    run_id: str
    started_at: datetime
    finished_at: datetime | None = None
    status: str = "running"
    report_path: str | None = None


class QueryStats(BaseModel):
    """クエリ実行統計"""

    run_id: str
    query_name: str
    status: str = "pending"
    fetched_count: int = 0
    parsed_count: int = 0
    inserted_count: int = 0
    matched_count: int = 0
    summarized_count: int = 0
    error_message: str | None = None
