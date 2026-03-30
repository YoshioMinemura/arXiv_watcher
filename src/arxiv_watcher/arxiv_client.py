"""arXiv API クライアント (§9 準拠)"""

from __future__ import annotations

import logging
import time

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://export.arxiv.org/api/query"

# リトライ対象のHTTPステータスコード
_RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
_MAX_RETRIES = 3
_BACKOFF_SECONDS = [2, 4, 8]
_TIMEOUT_SECONDS = 30.0


def fetch_arxiv(
    *,
    search_query: str,
    start: int = 0,
    max_results: int = 50,
    sort_by: str = "submittedDate",
    sort_order: str = "descending",
    user_agent: str = "arxiv-watcher/0.1",
) -> str:
    """arXiv API から Atom XML を取得する。

    Args:
        search_query: arXiv 検索クエリ文字列
        start: 取得開始位置
        max_results: 最大取得件数
        sort_by: ソート基準
        sort_order: ソート順
        user_agent: User-Agent ヘッダ

    Returns:
        Atom XML レスポンス文字列

    Raises:
        httpx.HTTPStatusError: リトライ後も失敗した場合
    """
    params = {
        "search_query": search_query,
        "start": start,
        "max_results": max_results,
        "sortBy": sort_by,
        "sortOrder": sort_order,
    }
    headers = {"User-Agent": user_agent}

    logger.info(
        "arXiv API リクエスト: search_query=%s, start=%d, max_results=%d",
        search_query,
        start,
        max_results,
    )
    logger.debug("Request URL: %s, params: %s", BASE_URL, params)

    last_exception: Exception | None = None

    for attempt in range(_MAX_RETRIES + 1):
        try:
            with httpx.Client(timeout=_TIMEOUT_SECONDS) as client:
                response = client.get(BASE_URL, params=params, headers=headers)
                response.raise_for_status()
                logger.info(
                    "arXiv API レスポンス取得成功 (%d bytes)",
                    len(response.text),
                )
                return response.text
        except httpx.HTTPStatusError as e:
            last_exception = e
            status_code = e.response.status_code
            if status_code in _RETRY_STATUS_CODES and attempt < _MAX_RETRIES:
                wait = _BACKOFF_SECONDS[attempt]
                logger.warning(
                    "arXiv API HTTP %d エラー。%d秒後にリトライ (%d/%d)",
                    status_code,
                    wait,
                    attempt + 1,
                    _MAX_RETRIES,
                )
                time.sleep(wait)
            else:
                raise
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            last_exception = e
            if attempt < _MAX_RETRIES:
                wait = _BACKOFF_SECONDS[attempt]
                logger.warning(
                    "arXiv API 通信エラー: %s。%d秒後にリトライ (%d/%d)",
                    type(e).__name__,
                    wait,
                    attempt + 1,
                    _MAX_RETRIES,
                )
                time.sleep(wait)
            else:
                raise

    # ここには到達しないはずだが念のため
    if last_exception:
        raise last_exception
    raise RuntimeError("Unexpected: no response and no exception")
