"""設定ファイル読み込み (§6 準拠)"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


# ── スコアリング設定 ──


class KeywordRule(BaseModel):
    keyword: str
    weight: float = 1.0


class CategoryRule(BaseModel):
    category: str
    weight: float = 1.0


class ScoringConfig(BaseModel):
    title_keyword_weight: float = 3.0
    abstract_keyword_weight: float = 1.5
    primary_category_weight: float = 2.0
    category_weight: float = 1.0
    keyword_rules: list[KeywordRule] = Field(default_factory=list)
    category_rules: list[CategoryRule] = Field(default_factory=list)


# ── デフォルト設定 ──


class DefaultsConfig(BaseModel):
    max_results: int = 50
    start: int = 0
    sort_by: str = "submittedDate"
    sort_order: str = "descending"
    request_delay_seconds: float = 3.1
    lookback_days: int = 2
    timezone: str = "Asia/Tokyo"
    report_top_n: int = 20
    user_agent: str = "arxiv-watcher/0.1"
    summarize: bool = True
    min_relevance_score: float = 1.0


# ── クエリ設定 ──


class QueryConfig(BaseModel):
    name: str
    enabled: bool = True
    search_query: str
    include_keywords: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    max_results: int | None = None
    min_relevance_score: float | None = None

    @field_validator("name")
    @classmethod
    def name_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("query name must not be empty")
        return v.strip()


# ── トップレベル設定 ──


class AppConfig(BaseModel):
    defaults: DefaultsConfig = Field(default_factory=DefaultsConfig)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    queries: list[QueryConfig] = Field(default_factory=list)

    def get_enabled_queries(self) -> list[QueryConfig]:
        """enabled: true のクエリのみ返す"""
        return [q for q in self.queries if q.enabled]

    def resolve_max_results(self, query: QueryConfig) -> int:
        """query 固有値がなければ defaults を返す"""
        return query.max_results if query.max_results is not None else self.defaults.max_results

    def resolve_min_relevance_score(self, query: QueryConfig) -> float:
        """query 固有値がなければ defaults を返す"""
        return (
            query.min_relevance_score
            if query.min_relevance_score is not None
            else self.defaults.min_relevance_score
        )


def load_config(path: Path) -> AppConfig:
    """YAMLファイルから設定を読み込む。

    不正な query は除外してログ出力し、正常な query のみ返す。
    """
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if raw is None:
        raw = {}

    # queries を個別にバリデーションし、不正なものは除外
    valid_queries: list[dict] = []
    raw_queries = raw.pop("queries", []) or []

    for i, q in enumerate(raw_queries):
        try:
            QueryConfig(**q)
            valid_queries.append(q)
        except Exception as e:
            name = q.get("name", f"index={i}")
            logger.warning("Query '%s' の設定が不正です。スキップします: %s", name, e)

    raw["queries"] = valid_queries
    return AppConfig(**raw)
