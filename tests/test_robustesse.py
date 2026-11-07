import pytest


class ReadTimeout(Exception):
    pass


class _M:
    def generate_content(self, **kw):
        raise ReadTimeout("x")


class _C:
    models = _M()


def test_timeout_leve_timeouterror(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    import modules.gemini_handler as gh
    monkeypatch.setattr(gh, "_CLIENTS", [_C()])
    with pytest.raises(TimeoutError):
        gh._appeler("x")


def test_champs_non_texte_pas_de_500(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    monkeypatch.setattr("modules.database.DB_PATH", tmp_path / "t.db")
    import app as appmod
    from modules.database import init_db
    from modules.chat_db import init_chat_db
    init_db()
    init_chat_db()
    c = appmod.app.test_client()
    r = c.post("/api/expose/section", json={"sujet": 123, "texte": 5, "consigne_perso": None, "plan": "abc"})
    assert r.status_code == 400


def test_erreur_timeout_504(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    monkeypatch.setattr("modules.database.DB_PATH", tmp_path / "t.db")
    import app as appmod
    with appmod.app.test_request_context():
        resp, code = appmod._erreur(TimeoutError("x"))
    assert code == 504
    assert "reessaie" in resp.get_json()["error"]
