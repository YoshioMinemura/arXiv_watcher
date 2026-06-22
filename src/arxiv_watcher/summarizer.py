"""LLM 要約 (§13 準拠)"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass

import httpx

from arxiv_watcher.utils import normalize_openai_base_url

logger = logging.getLogger(__name__)

# 要約結果
@dataclass
class SummaryResult:
    ja_summary: str | None = None
    novelty: str | None = None
    tags: list[str] | None = None


_SYSTEM_PROMPT = """\
あなたは研究者向けの論文要約アシスタントです。
以下のルールに従って、与えられた論文情報を日本語で要約してください。

ルール:
- 誇張禁止: abstract に書かれていないことを推測しすぎない
- 要約は2〜3文で簡潔に
- 新規性は1文で説明
- タグは3〜5個
- 出力は以下のJSON形式のみ:

{"ja_summary": "...", "novelty": "...", "tags": ["tag1", "tag2", "tag3"]}
"""


def is_summarization_available(summarize_enabled: bool) -> bool:
    """要約が有効か判定する。

    条件:
    - config の summarize: true
    - LLM_BACKEND=openai の場合は OPENAI_API_KEY と OPENAI_MODEL が存在
    - LLM_BACKEND=local の場合は LOCAL_LLM_MODEL が存在
    """
    if not summarize_enabled:
        return False

    backend = _resolve_backend()
    if backend == "local":
        if not os.environ.get("LOCAL_LLM_MODEL"):
            logger.info("LOCAL_LLM_MODEL が未設定のため、要約をスキップします")
            return False
        return True

    if not os.environ.get("OPENAI_API_KEY") or not os.environ.get("OPENAI_MODEL"):
        logger.info("OPENAI_API_KEY または OPENAI_MODEL が未設定のため、要約をスキップします")
        return False
    return True


def summarize_paper(
    title: str,
    summary: str,
    primary_category: str | None,
    categories: list[str],
) -> SummaryResult:
    """LLM で論文を日本語要約する。

    エラー時は空の SummaryResult を返す（致命的エラーにしない）。
    """
    user_content = _build_user_content(
        title=title,
        summary=summary,
        primary_category=primary_category,
        categories=categories,
    )

    if _resolve_backend() == "local":
        return _summarize_with_local(user_content)

    return _summarize_with_openai(user_content)


def _resolve_backend() -> str:
    backend = os.environ.get("LLM_BACKEND", "").strip().lower()
    if backend in {"openai", "local"}:
        return backend
    if os.environ.get("LOCAL_LLM_MODEL"):
        return "local"
    return "openai"


def _build_user_content(
    *,
    title: str,
    summary: str,
    primary_category: str | None,
    categories: list[str],
) -> str:
    return f"""\
タイトル: {title}

Abstract:
{summary}

Categories: {', '.join(categories)}
Primary Category: {primary_category or 'N/A'}
"""


def _summarize_with_openai(user_content: str) -> SummaryResult:
    try:
        from openai import OpenAI  # noqa: E402
    except ImportError:
        logger.warning("openai パッケージが未インストールです。要約をスキップします。")
        return SummaryResult()

    api_key = os.environ.get("OPENAI_API_KEY", "")
    raw_base_url = os.environ.get("OPENAI_BASE_URL")
    base_url = normalize_openai_base_url(raw_base_url)
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    try:
        client_kwargs: dict = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url

        client = OpenAI(**client_kwargs)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
            max_completion_tokens=500,
            timeout=30,
        )

        content = response.choices[0].message.content
        if not content:
            logger.warning("LLM からの空レスポンス")
            return SummaryResult()

        return _parse_summary_json(content)
    except Exception as e:
        status_code = getattr(e, "status_code", None)
        if status_code == 404:
            logger.warning(
                "LLM API が 404 を返しました (model=%s, OPENAI_BASE_URL=%s, normalized=%s)。"
                " モデル名が利用可能か、base URL が /v1 を含むかを確認してください。",
                model,
                raw_base_url or "<default>",
                base_url or "<default>",
            )
        logger.warning("LLM 要約中にエラーが発生しました: %s", e)
        return SummaryResult()


def _summarize_with_local(user_content: str) -> SummaryResult:
    try:
        endpoint = os.environ.get("LOCAL_LLM_ENDPOINT", "http://localhost:11434/api/generate")
        model = os.environ.get("LOCAL_LLM_MODEL", "")
        timeout = float(os.environ.get("LOCAL_LLM_TIMEOUT", "60"))
        prompt = f"{_SYSTEM_PROMPT}\n\n{user_content}"

        response = httpx.post(
            endpoint,
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.3},
            },
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        content = _extract_local_content(payload)
        if not content:
            logger.warning("local LLM からの空レスポンス")
            return SummaryResult()
        return _parse_summary_json(content)
    except Exception as e:
        logger.warning("local LLM 要約中にエラーが発生しました: %s", e)
        return SummaryResult()


def _extract_local_content(payload: dict) -> str | None:
    response_text = payload.get("response")
    if isinstance(response_text, str):
        return response_text

    message = payload.get("message")
    if isinstance(message, dict) and isinstance(message.get("content"), str):
        return message["content"]

    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                return message["content"]
            text = first.get("text")
            if isinstance(text, str):
                return text
    return None


def _parse_summary_json(content: str) -> SummaryResult:
    try:
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1]).strip()

        data = json.loads(content)
        tags = data.get("tags")
        if tags is not None and not isinstance(tags, list):
            tags = None
        return SummaryResult(
            ja_summary=data.get("ja_summary"),
            novelty=data.get("novelty"),
            tags=[str(tag) for tag in tags] if tags else None,
        )
    except json.JSONDecodeError as e:
        logger.warning("LLM レスポンスの JSON パースに失敗: %s", e)
        return SummaryResult()
