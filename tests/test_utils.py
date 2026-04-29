"""utils モジュールのテスト"""

from arxiv_watcher.utils import normalize_openai_base_url


def test_normalize_openai_base_url_adds_v1_for_openai() -> None:
    assert normalize_openai_base_url("https://api.openai.com") == "https://api.openai.com/v1"


def test_normalize_openai_base_url_keeps_existing_v1() -> None:
    assert normalize_openai_base_url("https://api.openai.com/v1") == "https://api.openai.com/v1"


def test_normalize_openai_base_url_adds_openai_v1_for_azure() -> None:
    url = "https://example-resource.openai.azure.com"
    assert normalize_openai_base_url(url) == "https://example-resource.openai.azure.com/openai/v1"


def test_normalize_openai_base_url_handles_none_or_empty() -> None:
    assert normalize_openai_base_url(None) is None
    assert normalize_openai_base_url("") is None
