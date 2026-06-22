"""cli モジュールのテスト"""

from arxiv_watcher.cli import _decode_categories


def test_decode_categories_from_json_string():
    assert _decode_categories('["cs.CL", "cs.AI"]') == ["cs.CL", "cs.AI"]


def test_decode_categories_rejects_invalid_json():
    assert _decode_categories("not-json") == []
