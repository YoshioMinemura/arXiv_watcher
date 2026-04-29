"""汎用ユーティリティ"""

from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse, urlunparse
from zoneinfo import ZoneInfo


def get_timezone(tz_name: str) -> ZoneInfo:
    """タイムゾーン名から ZoneInfo を取得する。"""
    return ZoneInfo(tz_name)


def now_local(tz_name: str = "Asia/Tokyo") -> datetime:
    """指定タイムゾーンの現在時刻を返す。"""
    tz = get_timezone(tz_name)
    return datetime.now(tz)


def now_utc() -> datetime:
    """UTC の現在時刻を返す。"""
    return datetime.now(timezone.utc)


def to_local(dt: datetime, tz_name: str = "Asia/Tokyo") -> datetime:
    """UTC datetime をローカルタイムゾーンに変換する。"""
    tz = get_timezone(tz_name)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(tz)


def normalize_whitespace(text: str) -> str:
    """連続する空白・改行を1つのスペースに畳み、前後空白を除去する。"""
    return re.sub(r"\s+", " ", text).strip()


def normalize_openai_base_url(base_url: str | None) -> str | None:
    """OpenAI 互換 API の base_url を正規化する。

    OPENAI_BASE_URL に /v1 が欠けていると 404 になりやすいため補完する。
    Azure OpenAI ドメインでは /openai/v1 を補完する。
    """
    if not base_url:
        return None

    raw = base_url.strip()
    if not raw:
        return None

    parsed = urlparse(raw)
    path = parsed.path.rstrip("/")

    if path.endswith("/v1"):
        return urlunparse(parsed._replace(path=path))

    if parsed.netloc.endswith("openai.azure.com"):
        new_path = f"{path}/openai/v1" if path else "/openai/v1"
    else:
        new_path = f"{path}/v1" if path else "/v1"

    return urlunparse(parsed._replace(path=new_path))


# arXiv ID 抽出パターン
# 新形式: 2503.12345 or 2503.12345v2
# 旧形式: hep-th/9901001 or hep-th/9901001v1
_ARXIV_ID_PATTERN = re.compile(
    r"(?:arxiv\.org/abs/|arxiv\.org/pdf/)?"
    r"(?P<id>"
    r"(?:\d{4}\.\d{4,5})"       # 新形式
    r"|(?:[a-z-]+/\d{7})"       # 旧形式
    r")"
    r"(?:v(?P<version>\d+))?"
)


def extract_arxiv_id(url_or_id: str) -> tuple[str, str, int | None]:
    """arXiv ID を抽出する。

    Returns:
        (paper_id_base, paper_id_full, version)
        抽出できなかった場合は元文字列をそのまま返す
    """
    m = _ARXIV_ID_PATTERN.search(url_or_id)
    if m:
        base_id = m.group("id")
        version = int(m.group("version")) if m.group("version") else None
        full_id = f"{base_id}v{version}" if version else base_id
        return base_id, full_id, version

    # パターンに合致しない場合はそのまま返す
    return url_or_id, url_or_id, None
