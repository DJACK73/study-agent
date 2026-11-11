import pytest


@pytest.fixture(autouse=True)
def _log_intent_isole(tmp_path, monkeypatch):
    monkeypatch.setattr("modules.chat_intent._LOG", str(tmp_path / "intent_log.jsonl"))


@pytest.fixture(autouse=True)
def _commons_isole(monkeypatch):
    from modules import commons
    commons._CACHE.clear()
    monkeypatch.setattr(commons, "_INTERVALLE", 0)
    yield
