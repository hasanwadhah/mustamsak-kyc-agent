import pytest


@pytest.fixture(autouse=True)
def no_local_vision_model(monkeypatch, tmp_path):
    """Tests never call a real local Ollama model or touch the user's saved settings."""
    from app import vision_llm
    monkeypatch.setenv('MUSTAMSAK_LOCAL_VLM', '0')
    monkeypatch.setattr(vision_llm, 'settings_file', lambda: tmp_path / 'settings.json')
    monkeypatch.setattr(vision_llm, '_available', None)
    monkeypatch.setattr(vision_llm, '_model_names', lambda: set())
    monkeypatch.setattr(vision_llm, '_ollama_version', lambda: None)
