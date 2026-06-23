"""Tests for application configuration loading."""

from app.config import load_config


def test_env_overrides_nested_ollama_config(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.1:8b")

    config = load_config()

    assert config.llm.ollama.base_url == "http://ollama:11434"
    assert config.llm.ollama.model == "llama3.1:8b"
