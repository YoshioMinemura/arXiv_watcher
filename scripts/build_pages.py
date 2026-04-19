"""Build a static GitHub Pages site from generated Markdown reports."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path
from shutil import rmtree


ROOT_DIR = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT_DIR / "reports"
DOCS_DIR = ROOT_DIR / "docs"
DOCS_REPORTS_DIR = DOCS_DIR / "reports"
DOCS_ASSETS_DIR = DOCS_DIR / "assets"


@dataclass
class ReportPage:
    slug: str
    title: str
    date: str
    generated_at: str
    run_id: str
    queries_executed: str
    total_matched: str
    source_path: Path
    output_path: Path
    html_content: str


def build_site() -> None:
    reports = sorted(REPORTS_DIR.glob("*.md"), reverse=True)

    DOCS_DIR.mkdir(exist_ok=True)
    DOCS_ASSETS_DIR.mkdir(exist_ok=True)
    if DOCS_REPORTS_DIR.exists():
        rmtree(DOCS_REPORTS_DIR)
    DOCS_REPORTS_DIR.mkdir()

    pages: list[ReportPage] = []
    for report_path in reports:
        markdown_text = report_path.read_text(encoding="utf-8")
        page = build_report_page(report_path, markdown_text)
        page.output_path.write_text(render_report_html(page), encoding="utf-8")
        pages.append(page)

    write_assets()
    write_index(pages)
    (DOCS_DIR / ".nojekyll").write_text("", encoding="utf-8")


def build_report_page(report_path: Path, markdown_text: str) -> ReportPage:
    slug = report_path.stem
    title = extract_heading(markdown_text) or f"arXiv Daily Digest - {slug}"
    generated_at = extract_value(markdown_text, "Generated at:") or "N/A"
    run_id = extract_value(markdown_text, "Run ID:") or "N/A"
    queries_executed = extract_summary_value(markdown_text, "Queries executed")
    total_matched = extract_summary_value(markdown_text, "New matched papers")
    output_path = DOCS_REPORTS_DIR / f"{slug}.html"

    return ReportPage(
        slug=slug,
        title=title,
        date=slug,
        generated_at=generated_at,
        run_id=run_id,
        queries_executed=queries_executed,
        total_matched=total_matched,
        source_path=report_path,
        output_path=output_path,
        html_content=markdown_to_html(markdown_text),
    )


def extract_heading(markdown_text: str) -> str | None:
    for line in markdown_text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


def extract_value(markdown_text: str, prefix: str) -> str | None:
    for line in markdown_text.splitlines():
        if line.startswith(prefix):
            return line.split(":", 1)[1].strip()
    return None


def extract_summary_value(markdown_text: str, label: str) -> str:
    prefix = f"- {label}:"
    for line in markdown_text.splitlines():
        if line.startswith(prefix):
            return line.split(":", 1)[1].strip()
    return "0"


def markdown_to_html(markdown_text: str) -> str:
    lines = markdown_text.splitlines()
    blocks: list[str] = []
    paragraph_lines: list[str] = []
    list_stack: list[int] = []

    def flush_paragraph() -> None:
        if paragraph_lines:
            text = " ".join(line.strip() for line in paragraph_lines)
            blocks.append(f"<p>{format_inline(text)}</p>")
            paragraph_lines.clear()

    def close_lists(target_level: int = 0) -> None:
        while list_stack and list_stack[-1] >= target_level:
            blocks.append("</ul>")
            list_stack.pop()

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()

        if not stripped:
            flush_paragraph()
            close_lists()
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading_match:
            flush_paragraph()
            close_lists()
            level = len(heading_match.group(1))
            blocks.append(f"<h{level}>{format_inline(heading_match.group(2).strip())}</h{level}>")
            continue

        if stripped == "---":
            flush_paragraph()
            close_lists()
            blocks.append("<hr />")
            continue

        if stripped.startswith("> "):
            flush_paragraph()
            close_lists()
            quote_text = stripped[2:].strip()
            blocks.append(f"<blockquote><p>{format_inline(quote_text)}</p></blockquote>")
            continue

        list_match = re.match(r"^(\s*)-\s+(.*)$", line)
        if list_match:
            flush_paragraph()
            indent = len(list_match.group(1)) // 2
            content = list_match.group(2).strip()

            while list_stack and list_stack[-1] > indent:
                blocks.append("</ul>")
                list_stack.pop()

            if not list_stack or list_stack[-1] < indent:
                blocks.append("<ul>")
                list_stack.append(indent)

            blocks.append(f"<li>{format_inline(content)}</li>")
            continue

        close_lists()
        paragraph_lines.append(line)

    flush_paragraph()
    close_lists()
    return "\n".join(blocks)


def format_inline(text: str) -> str:
    escaped = html.escape(text, quote=False)
    escaped = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda m: f'<a href="{html.escape(m.group(2), quote=True)}">{m.group(1)}</a>',
        escaped,
    )
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    return escaped


def render_report_html(page: ReportPage) -> str:
    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(page.title)} | arxiv-watcher</title>
  <link rel="stylesheet" href="../assets/style.css" />
</head>
<body>
  <main class="page-shell">
    <header class="site-header">
      <a class="site-home" href="../index.html">arxiv-watcher reports</a>
      <p class="site-subtitle">Daily arXiv digests published from GitHub Actions</p>
    </header>

    <section class="hero hero-compact">
      <div>
        <p class="eyebrow">Daily Report</p>
        <h1>{html.escape(page.title)}</h1>
        <p class="hero-copy">Generated at {html.escape(page.generated_at)}. Run ID: <code>{html.escape(page.run_id)}</code></p>
      </div>
      <div class="stats-grid">
        <div class="stat-card">
          <span class="stat-label">Queries</span>
          <strong>{html.escape(page.queries_executed)}</strong>
        </div>
        <div class="stat-card">
          <span class="stat-label">Matched Papers</span>
          <strong>{html.escape(page.total_matched)}</strong>
        </div>
      </div>
    </section>

    <article class="report-card markdown-body">
{indent_html(page.html_content, 6)}
    </article>
  </main>
</body>
</html>
"""


def write_index(pages: list[ReportPage]) -> None:
    latest = pages[0] if pages else None
    archive_items = "\n".join(
        f"""      <a class="archive-item" href="reports/{html.escape(page.slug)}.html">
        <div>
          <strong>{html.escape(page.date)}</strong>
          <p>{html.escape(page.title)}</p>
        </div>
        <span>{html.escape(page.total_matched)} papers</span>
      </a>"""
        for page in pages
    )

    latest_section = ""
    if latest is not None:
        latest_section = f"""
    <section class="panel">
      <div class="panel-header">
        <div>
          <p class="eyebrow">Latest Digest</p>
          <h2>{html.escape(latest.date)}</h2>
        </div>
        <a class="button-link" href="reports/{html.escape(latest.slug)}.html">Open report</a>
      </div>
      <div class="stats-grid">
        <div class="stat-card">
          <span class="stat-label">Generated</span>
          <strong>{html.escape(latest.generated_at)}</strong>
        </div>
        <div class="stat-card">
          <span class="stat-label">Queries</span>
          <strong>{html.escape(latest.queries_executed)}</strong>
        </div>
        <div class="stat-card">
          <span class="stat-label">Matched Papers</span>
          <strong>{html.escape(latest.total_matched)}</strong>
        </div>
      </div>
    </section>
"""

    if not archive_items:
        archive_items = '      <p class="empty-state">No reports have been published yet.</p>'

    html_text = f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>arxiv-watcher reports</title>
  <link rel="stylesheet" href="assets/style.css" />
</head>
<body>
  <main class="page-shell">
    <header class="site-header">
      <a class="site-home" href="index.html">arxiv-watcher reports</a>
      <p class="site-subtitle">Browse daily arXiv digests published from this repository.</p>
    </header>

    <section class="hero">
      <div>
        <p class="eyebrow">GitHub Pages</p>
        <h1>Daily arXiv reports in your browser</h1>
        <p class="hero-copy">This site publishes the Markdown digests stored in <code>reports/</code> as a lightweight archive you can browse without cloning the repository.</p>
      </div>
    </section>
{latest_section}
    <section class="panel">
      <div class="panel-header">
        <div>
          <p class="eyebrow">Archive</p>
          <h2>All reports</h2>
        </div>
      </div>
      <div class="archive-list">
{archive_items}
      </div>
    </section>
  </main>
</body>
</html>
"""
    (DOCS_DIR / "index.html").write_text(html_text, encoding="utf-8")


def write_assets() -> None:
    css = """\
:root {
  color-scheme: light;
  --bg: #f6f3eb;
  --surface: rgba(255, 252, 246, 0.92);
  --surface-strong: #fffdf9;
  --text: #1f2933;
  --muted: #5f6c74;
  --line: rgba(31, 41, 51, 0.12);
  --accent: #0f766e;
  --accent-strong: #134e4a;
  --shadow: 0 24px 48px rgba(31, 41, 51, 0.08);
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  font-family: "Segoe UI", "Hiragino Sans", "Noto Sans JP", sans-serif;
  color: var(--text);
  background:
    radial-gradient(circle at top left, rgba(15, 118, 110, 0.12), transparent 32%),
    linear-gradient(180deg, #faf8f1 0%, #f1ece1 100%);
  line-height: 1.7;
}

a {
  color: var(--accent-strong);
}

code {
  padding: 0.1rem 0.35rem;
  border-radius: 0.35rem;
  background: rgba(15, 118, 110, 0.08);
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 0.95em;
}

.page-shell {
  width: min(1100px, calc(100% - 2rem));
  margin: 0 auto;
  padding: 2rem 0 4rem;
}

.site-header {
  margin-bottom: 1.5rem;
}

.site-home {
  color: var(--text);
  text-decoration: none;
  font-weight: 700;
  letter-spacing: 0.02em;
}

.site-subtitle {
  margin: 0.4rem 0 0;
  color: var(--muted);
}

.hero,
.panel,
.report-card {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 1.5rem;
  box-shadow: var(--shadow);
}

.hero,
.panel {
  padding: 1.5rem;
  margin-bottom: 1.25rem;
}

.hero {
  display: grid;
  gap: 1rem;
}

.hero-compact {
  grid-template-columns: 1.8fr 1fr;
  align-items: start;
}

.eyebrow {
  margin: 0 0 0.5rem;
  color: var(--accent);
  font-size: 0.85rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.hero h1,
.panel h2 {
  margin: 0;
  line-height: 1.2;
}

.hero-copy {
  margin: 0.85rem 0 0;
  color: var(--muted);
}

.panel-header {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: center;
  margin-bottom: 1rem;
}

.button-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0.7rem 1rem;
  border-radius: 999px;
  background: var(--accent);
  color: white;
  text-decoration: none;
  font-weight: 700;
}

.stats-grid {
  display: grid;
  gap: 0.9rem;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
}

.stat-card {
  padding: 1rem;
  border-radius: 1rem;
  background: var(--surface-strong);
  border: 1px solid var(--line);
}

.stat-card strong {
  display: block;
  margin-top: 0.25rem;
  font-size: 1.1rem;
}

.stat-label {
  color: var(--muted);
  font-size: 0.85rem;
}

.archive-list {
  display: grid;
  gap: 0.85rem;
}

.archive-item {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: center;
  padding: 1rem 1.1rem;
  border-radius: 1rem;
  background: var(--surface-strong);
  border: 1px solid var(--line);
  text-decoration: none;
  color: inherit;
}

.archive-item p {
  margin: 0.2rem 0 0;
  color: var(--muted);
}

.empty-state {
  margin: 0;
  color: var(--muted);
}

.report-card {
  padding: 1.75rem;
}

.markdown-body h1,
.markdown-body h2,
.markdown-body h3 {
  line-height: 1.25;
  margin-top: 1.8rem;
  margin-bottom: 0.8rem;
}

.markdown-body h1:first-child,
.markdown-body h2:first-child,
.markdown-body h3:first-child {
  margin-top: 0;
}

.markdown-body p,
.markdown-body ul,
.markdown-body blockquote {
  margin-top: 0;
  margin-bottom: 1rem;
}

.markdown-body ul {
  padding-left: 1.4rem;
}

.markdown-body li + li {
  margin-top: 0.2rem;
}

.markdown-body blockquote {
  padding: 0.1rem 1rem;
  border-left: 4px solid rgba(15, 118, 110, 0.45);
  background: rgba(15, 118, 110, 0.06);
  border-radius: 0 0.8rem 0.8rem 0;
}

.markdown-body hr {
  border: 0;
  border-top: 1px solid var(--line);
  margin: 1.5rem 0;
}

@media (max-width: 760px) {
  .page-shell {
    width: min(100% - 1rem, 1100px);
    padding-top: 1rem;
  }

  .hero-compact,
  .panel-header,
  .archive-item {
    grid-template-columns: 1fr;
    display: grid;
  }

  .archive-item {
    justify-content: start;
  }
}
"""
    (DOCS_ASSETS_DIR / "style.css").write_text(css, encoding="utf-8")


def indent_html(content: str, spaces: int) -> str:
    prefix = " " * spaces
    return "\n".join(f"{prefix}{line}" if line else "" for line in content.splitlines())


if __name__ == "__main__":
    build_site()
