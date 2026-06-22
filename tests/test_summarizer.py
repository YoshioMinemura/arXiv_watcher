"""summarizer モジュールのテスト"""

from arxiv_watcher.summarizer import (
    _parse_summary_json,
    _resolve_backend,
    is_summarization_available,
)


def test_local_backend_is_available_with_model(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "local")
    monkeypatch.setenv("LOCAL_LLM_MODEL", "gemma3")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    assert _resolve_backend() == "local"
    assert is_summarization_available(True) is True


def test_openai_backend_requires_key_and_model(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")

    assert _resolve_backend() == "openai"
    assert is_summarization_available(True) is True


def test_parse_summary_json_accepts_code_block():
    result = _parse_summary_json(
        """```json
{"ja_summary": "要約", "novelty": "新規性", "tags": ["llm", "math"]}
```"""
    )

    assert result.ja_summary == "要約"
    assert result.novelty == "新規性"
    assert result.tags == ["llm", "math"]
