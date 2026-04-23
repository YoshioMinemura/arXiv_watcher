"""Discord webhook notification for the latest arXiv digest."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime

import httpx
from dotenv import load_dotenv

from arxiv_watcher.storage import Storage
from arxiv_watcher.utils import to_local

DISCORD_MAX_CONTENT = 1900
DEFAULT_MAX_PAPERS = 20


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Post the latest arXiv digest to Discord."
    )
    parser.add_argument("--db-path", default="data/arxiv.db")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--webhook-url", default=None)
    parser.add_argument("--timezone", default="Asia/Tokyo")
    parser.add_argument("--max-papers", type=int, default=DEFAULT_MAX_PAPERS)
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()

    webhook_url = args.webhook_url or os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        raise SystemExit("DISCORD_WEBHOOK_URL is not set.")

    storage = Storage(args.db_path)
    storage.init_db()

    try:
        run_id = args.run_id or storage.get_latest_run_id()
        if not run_id:
            raise SystemExit("No run history found.")

        matches_data = storage.get_matches_for_run(run_id)
        query_stats = storage.get_query_stats_for_run(run_id)
        messages = build_messages(
            run_id=run_id,
            matches_data=matches_data,
            query_stats=query_stats,
            tz_name=args.timezone,
            max_papers=max(1, args.max_papers),
        )
    finally:
        storage.close()

    send_messages(webhook_url, messages)


def build_messages(
    *,
    run_id: str,
    matches_data: list[dict],
    query_stats: list,
    tz_name: str,
    max_papers: int,
) -> list[str]:
    now = to_local(datetime.utcnow(), tz_name)
    date_str = now.strftime("%Y-%m-%d %H:%M %Z")

    queries_map: dict[str, list[dict]] = {}
    for match in matches_data:
        queries_map.setdefault(match["query_name"], []).append(match)

    stats_map = {stat.query_name: stat for stat in query_stats}
    query_names = list(dict.fromkeys(
        [stat.query_name for stat in query_stats] + list(queries_map.keys())
    ))

    total_matched = sum(len(queries_map.get(name, [])) for name in query_names)
    blocks = [
        "\n".join(
            [
                f"**arXiv Daily Digest ({date_str})**",
                f"Run ID: `{run_id}`",
                f"クエリ数: {len(query_names)}",
                f"該当論文数: {total_matched}",
            ]
        )
    ]

    for query_name in query_names:
        stat = stats_map.get(query_name)
        matches = queries_map.get(query_name, [])

        if stat and stat.status == "failed":
            blocks.append(
                "\n".join(
                    [
                        f"**{query_name}**",
                        f"取得に失敗しました: {truncate_text(stat.error_message or 'Unknown error', 300)}",
                    ]
                )
            )
            continue

        if not matches:
            blocks.append(f"**{query_name}**\n該当論文はありませんでした。")
            continue

        blocks.append(
            f"**{query_name}**\n{len(matches)} 件ヒット。上位 {min(len(matches), max_papers)} 件を送信します。"
        )

        for index, match in enumerate(matches[:max_papers], start=1):
            blocks.append(format_paper_block(index, match))

        omitted = len(matches) - min(len(matches), max_papers)
        if omitted > 0:
            blocks.append(f"**{query_name}**\nほか {omitted} 件は GitHub 上のレポートに残しています。")

    return chunk_blocks(blocks, DISCORD_MAX_CONTENT)


def format_paper_block(index: int, match: dict) -> str:
    title = sanitize_inline(match.get("title") or "Untitled")
    summary_ja = sanitize_inline(match.get("llm_summary_ja") or "日本語要約は生成されませんでした。")
    novelty_ja = sanitize_inline(match.get("llm_novelty_ja") or "")
    tags = decode_json_list(match.get("llm_tags_json"))
    categories = decode_json_list(match.get("categories_json"))
    link = match.get("abs_url") or f"https://arxiv.org/abs/{match['paper_id_base']}"

    lines = [
        f"**{index}. {truncate_text(title, 180)}**",
        f"要約: {truncate_text(summary_ja, 420)}",
    ]

    if novelty_ja:
        lines.append(f"新規性: {truncate_text(novelty_ja, 220)}")
    if tags:
        lines.append(f"タグ: {', '.join(tags[:5])}")
    if categories:
        lines.append(f"カテゴリ: {', '.join(categories[:4])}")
    lines.append(f"リンク: {link}")
    return "\n".join(lines)


def decode_json_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return []
        if isinstance(decoded, list):
            return [str(item) for item in decoded]
    return []


def chunk_blocks(blocks: list[str], max_chars: int) -> list[str]:
    messages: list[str] = []
    current = ""

    for block in blocks:
        normalized = block.strip()
        if not normalized:
            continue

        if len(normalized) > max_chars:
            normalized = truncate_text(normalized, max_chars - 3)

        candidate = normalized if not current else f"{current}\n\n{normalized}"
        if len(candidate) <= max_chars:
            current = candidate
            continue

        if current:
            messages.append(current)
        current = normalized

    if current:
        messages.append(current)

    return messages


def send_messages(webhook_url: str, messages: list[str]) -> None:
    with httpx.Client(timeout=30.0) as client:
        for content in messages:
            response = client.post(webhook_url, json={"content": content})
            response.raise_for_status()


def sanitize_inline(text: str) -> str:
    return " ".join(text.split())


def truncate_text(text: str, max_length: int) -> str:
    normalized = sanitize_inline(text)
    if len(normalized) <= max_length:
        return normalized
    return normalized[: max_length - 3].rstrip() + "..."


if __name__ == "__main__":
    main()
