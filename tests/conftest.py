import pytest


@pytest.fixture(autouse=True)
def _log_intent_isole(tmp_path, monkeypatch):
    monkeypatch.setattr("modules.chat_intent._LOG", str(tmp_path / "intent_log.jsonl"))
