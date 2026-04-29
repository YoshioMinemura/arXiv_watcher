"""LLM 要約 (§13 準拠)"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass

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
    - 環境変数 OPENAI_API_KEY が存在
    - OPENAI_MODEL が存在
    """
    if not summarize_enabled:
        return False
    if not os.environ.get("OPENAI_API_KEY"):
        logger.info("OPENAI_API_KEY が未設定のため、要約をスキップします")
        return False
    if not os.environ.get("OPENAI_MODEL"):
        logger.info("OPENAI_MODEL が未設定のため、要約をスキップします")
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
    try:
        from openai import OpenAI  # noqa: E402
    except ImportError:
        logger.warning("openai パッケージが未インストールです。要約をスキップします。")
        return SummaryResult()

    api_key = os.environ.get("OPENAI_API_KEY", "")
    raw_base_url = os.environ.get("OPENAI_BASE_URL")
    base_url = normalize_openai_base_url(raw_base_url)
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    user_content = f"""\
タイトル: {title}

Abstract:
{summary}

Categories: {', '.join(categories)}
Primary Category: {primary_category or 'N/A'}
"""

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
            max_tokens=500,
            timeout=30,
        )

        content = response.choices[0].message.content
        if not content:
            logger.warning("LLM からの空レスポンス")
            return SummaryResult()

        # JSON パース
        # コードブロックで囲まれている場合に対応
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1])

        data = json.loads(content)
        return SummaryResult(
            ja_summary=data.get("ja_summary"),
            novelty=data.get("novelty"),
            tags=data.get("tags"),
        )

    except json.JSONDecodeError as e:
        logger.warning("LLM レスポンスの JSON パースに失敗: %s", e)
        return SummaryResult()
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
