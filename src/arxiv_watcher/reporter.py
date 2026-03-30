"""レポート生成 (§14 準拠)"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from arxiv_watcher.utils import to_local

logger = logging.getLogger(__name__)

# テンプレートディレクトリが見つからない場合の内蔵テンプレート
_BUILTIN_TEMPLATE = """\
# arXiv Daily Digest - {{ date }}

Generated at: {{ generated_at }}
Run ID: {{ run_id }}

## Summary
- Queries executed: {{ queries_executed }}
- New matched papers: {{ total_matched }}
{% for query in query_results %}

## Query: {{ query.name }}
{% if query.status == "failed" %}
> ⚠️ This query failed: {{ query.error_message or "Unknown error" }}
{% elif query.matches|length == 0 %}
> No matched papers.
{% else %}
{% for m in query.matches %}

### {{ loop.index }}. {{ m.title }}
- arXiv: [{{ m.paper_id_base }}](https://arxiv.org/abs/{{ m.paper_id_base }})
- PDF: [link](https://arxiv.org/pdf/{{ m.paper_id_base }}.pdf)
- Published: {{ m.published_at }}
- Updated: {{ m.updated_at }}
- Authors: {{ m.authors }}
- Categories: {{ m.categories }}
- Score: {{ "%.2f"|format(m.relevance_score) }}
- Match reasons:
{% for reason in m.match_reasons %}  - {{ reason }}
{% endfor %}
{% if m.llm_summary_ja %}
**日本語要約**
{{ m.llm_summary_ja }}
{% endif %}
{% if m.llm_novelty_ja %}
**新規性**
{{ m.llm_novelty_ja }}
{% endif %}
{% if m.llm_tags %}
**Tags:** {{ m.llm_tags|join(", ") }}
{% endif %}

**Abstract**
{{ m.summary }}

---
{% endfor %}
{% if query.omitted > 0 %}
> ... and {{ query.omitted }} more papers (not shown).
{% endif %}
{% endif %}
{% endfor %}
"""


def generate_report(
    *,
    run_id: str,
    matches_data: list[dict],
    query_stats: list,
    tz_name: str = "Asia/Tokyo",
    report_top_n: int = 20,
    output_dir: Path | None = None,
    template_dir: Path | None = None,
) -> Path:
    """Markdown レポートを生成して保存する。

    Args:
        run_id: 実行ID
        matches_data: Storage.get_matches_for_run() の結果
        query_stats: QueryStats リスト
        tz_name: 表示用タイムゾーン
        report_top_n: query ごとの最大表示件数
        output_dir: 出力ディレクトリ
        template_dir: Jinja2 テンプレートディレクトリ

    Returns:
        生成されたレポートファイルのパス
    """
    now = to_local(datetime.utcnow(), tz_name)
    date_str = now.strftime("%Y-%m-%d")
    generated_at = now.strftime("%Y-%m-%d %H:%M %Z")

    if output_dir is None:
        output_dir = Path("reports")
    output_dir.mkdir(parents=True, exist_ok=True)

    # クエリ別にマッチデータを整理
    queries_map: dict[str, list[dict]] = {}
    for m in matches_data:
        qname = m["query_name"]
        if qname not in queries_map:
            queries_map[qname] = []
        queries_map[qname].append(m)

    # クエリ統計マップ
    stats_map = {s.query_name: s for s in query_stats}

    # テンプレートコンテキスト構築
    query_results = []
    total_matched = 0

    all_query_names = list(dict.fromkeys(
        [s.query_name for s in query_stats] + list(queries_map.keys())
    ))

    for qname in all_query_names:
        stat = stats_map.get(qname)
        raw_matches = queries_map.get(qname, [])

        if stat and stat.status == "failed":
            query_results.append({
                "name": qname,
                "status": "failed",
                "error_message": stat.error_message,
                "matches": [],
                "omitted": 0,
            })
            continue

        # マッチデータを表示用に整形
        formatted = []
        for m in raw_matches:
            formatted.append({
                "paper_id_base": m["paper_id_base"],
                "paper_id_full": m.get("paper_id_full", m["paper_id_base"]),
                "title": m["title"],
                "summary": m["summary"],
                "authors": ", ".join(json.loads(m["authors_json"]))
                    if isinstance(m["authors_json"], str) else ", ".join(m.get("authors_json", [])),
                "categories": ", ".join(json.loads(m["categories_json"]))
                    if isinstance(m["categories_json"], str) else ", ".join(m.get("categories_json", [])),
                "primary_category": m.get("primary_category", ""),
                "published_at": _format_datetime(m.get("published_at", ""), tz_name),
                "updated_at": _format_datetime(m.get("updated_at", ""), tz_name),
                "relevance_score": m["relevance_score"],
                "match_reasons": json.loads(m["match_reasons_json"])
                    if isinstance(m["match_reasons_json"], str) else m.get("match_reasons_json", []),
                "llm_summary_ja": m.get("llm_summary_ja"),
                "llm_novelty_ja": m.get("llm_novelty_ja"),
                "llm_tags": json.loads(m["llm_tags_json"])
                    if m.get("llm_tags_json") and isinstance(m["llm_tags_json"], str)
                    else m.get("llm_tags_json"),
                "pdf_url": m.get("pdf_url", ""),
                "abs_url": m.get("abs_url", ""),
            })

        shown = formatted[:report_top_n]
        omitted = len(formatted) - len(shown)
        total_matched += len(formatted)

        query_results.append({
            "name": qname,
            "status": "success",
            "error_message": None,
            "matches": shown,
            "omitted": omitted,
        })

    context = {
        "date": date_str,
        "generated_at": generated_at,
        "run_id": run_id,
        "queries_executed": len(all_query_names),
        "total_matched": total_matched,
        "query_results": query_results,
    }

    # テンプレートレンダリング
    md_content = _render_template(context, template_dir)

    # ファイル保存
    output_path = output_dir / f"{date_str}.md"
    output_path.write_text(md_content, encoding="utf-8")
    logger.info("レポート生成完了: %s", output_path)

    return output_path


def _render_template(context: dict, template_dir: Path | None) -> str:
    """Jinja2 でレンダリングする。テンプレートファイルがなければ内蔵テンプレートを使う。"""
    if template_dir and (template_dir / "daily_report.md.j2").exists():
        env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            keep_trailing_newline=True,
        )
        template = env.get_template("daily_report.md.j2")
    else:
        env = Environment(keep_trailing_newline=True)
        template = env.from_string(_BUILTIN_TEMPLATE)

    return template.render(**context)


def _format_datetime(dt_str: str, tz_name: str) -> str:
    """日時文字列をローカルタイムゾーンでフォーマットする。"""
    if not dt_str:
        return "N/A"
    try:
        dt = datetime.fromisoformat(dt_str)
        local_dt = to_local(dt, tz_name)
        return local_dt.strftime("%Y-%m-%d %H:%M %Z")
    except (ValueError, AttributeError):
        return dt_str
