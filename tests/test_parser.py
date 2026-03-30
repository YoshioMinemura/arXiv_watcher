"""parser モジュールのテスト"""

from pathlib import Path

from arxiv_watcher.parser import parse_feed


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def test_parse_sample_feed():
    """sample feed を正しく Paper に変換できる"""
    xml_text = (FIXTURE_DIR / "sample_feed.xml").read_text(encoding="utf-8")
    papers = parse_feed(xml_text)

    assert len(papers) == 3


def test_parse_paper_fields():
    """各フィールドが正しく抽出される"""
    xml_text = (FIXTURE_DIR / "sample_feed.xml").read_text(encoding="utf-8")
    papers = parse_feed(xml_text)

    # 最初のエントリ
    p = papers[0]
    assert p.paper_id_base == "2503.12345"
    assert p.paper_id_full == "2503.12345v2"
    assert p.version == 2
    assert "Large Language Models" in p.title
    assert "comprehensive survey" in p.summary
    assert len(p.authors) == 3
    assert "Alice Smith" in p.authors
    assert p.primary_category == "cs.CL"
    assert "cs.AI" in p.categories
    assert "cs.LG" in p.categories
    assert p.comment == "25 pages, 10 figures"


def test_parse_paper_urls():
    """PDF/abstract URLが正しく抽出される"""
    xml_text = (FIXTURE_DIR / "sample_feed.xml").read_text(encoding="utf-8")
    papers = parse_feed(xml_text)

    p = papers[0]
    assert p.pdf_url is not None
    assert "pdf" in p.pdf_url
    assert "2503.12345" in p.abs_url


def test_parse_optional_fields():
    """DOI, journal_ref が抽出される"""
    xml_text = (FIXTURE_DIR / "sample_feed.xml").read_text(encoding="utf-8")
    papers = parse_feed(xml_text)

    # 3番目のエントリにDOIとjournal_refがある
    p = papers[2]
    assert p.paper_id_base == "2503.11111"
    assert p.doi == "10.1234/example.2026"
    assert p.journal_ref == "Proceedings of ACL 2026"


def test_whitespace_normalization():
    """タイトル・要旨の空白が正規化される"""
    xml_text = (FIXTURE_DIR / "sample_feed.xml").read_text(encoding="utf-8")
    papers = parse_feed(xml_text)

    for p in papers:
        assert "\n" not in p.title
        assert "  " not in p.title
        assert "\n" not in p.summary
        assert "  " not in p.summary
