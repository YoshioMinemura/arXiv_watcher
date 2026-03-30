"""Atom XML パーサー (§10 準拠)"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import feedparser

from arxiv_watcher.models import Paper
from arxiv_watcher.utils import extract_arxiv_id, normalize_whitespace

logger = logging.getLogger(__name__)


def parse_feed(xml_text: str) -> list[Paper]:
    """Atom XML feed をパースして Paper リストを返す。

    パースに失敗した個別 entry はスキップして warning ログを出す。
    """
    feed = feedparser.parse(xml_text)

    if feed.bozo and not feed.entries:
        logger.error("XML パースエラー: %s", feed.bozo_exception)
        raise ValueError(f"Failed to parse Atom feed: {feed.bozo_exception}")

    papers: list[Paper] = []
    for entry in feed.entries:
        try:
            paper = _parse_entry(entry)
            papers.append(paper)
        except Exception as e:
            entry_id = getattr(entry, "id", "unknown")
            logger.warning("Entry '%s' のパースに失敗しました。スキップします: %s", entry_id, e)

    logger.info("パース完了: %d / %d entries を変換", len(papers), len(feed.entries))
    return papers


def _parse_entry(entry: feedparser.FeedParserDict) -> Paper:
    """個別の feed entry を Paper に変換する。"""
    # arXiv ID 抽出
    entry_id = entry.get("id", "")
    paper_id_base, paper_id_full, version = extract_arxiv_id(entry_id)

    # タイトル・要旨の正規化
    title = normalize_whitespace(entry.get("title", ""))
    summary = normalize_whitespace(entry.get("summary", ""))

    if not title:
        raise ValueError(f"Entry has no title: {entry_id}")

    # 著者
    authors_raw = entry.get("authors", [])
    authors = list(dict.fromkeys(
        a.get("name", "").strip() for a in authors_raw if a.get("name", "").strip()
    ))

    # カテゴリ
    tags = entry.get("tags", [])
    categories = list(dict.fromkeys(
        t.get("term", "").strip() for t in tags if t.get("term", "").strip()
    ))

    # primary_category
    primary_cat = None
    arxiv_primary = entry.get("arxiv_primary_category", {})
    if arxiv_primary:
        primary_cat = arxiv_primary.get("term", "").strip() or None
    if not primary_cat and categories:
        primary_cat = categories[0]

    # 日時
    published_at = _parse_datetime(entry.get("published", ""))
    updated_at = _parse_datetime(entry.get("updated", "")) or published_at

    # リンク
    pdf_url = None
    abs_url = entry_id
    for link in entry.get("links", []):
        href = link.get("href", "")
        link_type = link.get("type", "")
        link_title = link.get("title", "")
        if link_type == "application/pdf" or link_title == "pdf":
            pdf_url = href
        elif link_type == "text/html" or link.get("rel") == "alternate":
            abs_url = href

    # オプションフィールド
    doi = entry.get("arxiv_doi", None)
    comment = entry.get("arxiv_comment", None)
    journal_ref = entry.get("arxiv_journal_ref", None)

    if comment:
        comment = normalize_whitespace(comment)
    if journal_ref:
        journal_ref = normalize_whitespace(journal_ref)

    # 生データ保存用（JSON互換に変換）
    raw_entry = _entry_to_dict(entry)

    return Paper(
        paper_id_base=paper_id_base,
        paper_id_full=paper_id_full,
        version=version,
        title=title,
        summary=summary,
        authors=authors,
        primary_category=primary_cat,
        categories=categories,
        published_at=published_at,
        updated_at=updated_at,
        pdf_url=pdf_url,
        abs_url=abs_url,
        doi=doi,
        comment=comment,
        journal_ref=journal_ref,
        raw_entry_json=raw_entry,
    )


def _parse_datetime(dt_str: str) -> datetime:
    """ISO 8601 形式の日時文字列を datetime に変換する。"""
    if not dt_str:
        return datetime.now(timezone.utc)
    try:
        # feedparser は time.struct_time を返すこともある
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, AttributeError):
        return datetime.now(timezone.utc)


def _entry_to_dict(entry: feedparser.FeedParserDict) -> dict:
    """feedparser の entry を JSON シリアライズ可能な dict に変換する。"""
    try:
        # feedparser の FeedParserDict は通常 dict に変換可能
        raw = dict(entry)
        # json.dumps で検証（非シリアライズ可能なものを除去）
        json.dumps(raw, default=str)
        return raw
    except (TypeError, ValueError):
        # 最低限の情報だけ保存
        return {
            "id": entry.get("id", ""),
            "title": entry.get("title", ""),
        }
