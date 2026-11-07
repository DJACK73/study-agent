import pytest


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    monkeypatch.setattr("modules.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("modules.chat_intent._LOG", str(tmp_path / "log.jsonl"))
    monkeypatch.setattr("modules.chat_routes.UPLOAD_DIR", tmp_path / "up")
    import app as appmod
    from modules.database import init_db
    from modules.chat_db import init_chat_db
    init_db()
    init_chat_db()
    return appmod.app.test_client()


def _creer(c):
    j = c.post("/api/chat/conversations", json={}).get_json() or {}
    cid = j.get("id") or (j.get("conversation") or {}).get("id")
    assert cid is not None, "id de conversation introuvable dans %r" % j
    return cid


@pytest.mark.parametrize("exc,code", [
    (TimeoutError("x"), 504),
    (RuntimeError("x"), 502),
])
def test_chat_erreur_gemini_rien_sauvegarde(ctx, monkeypatch, exc, code):
    c = ctx
    cid = _creer(c)

    def boom(*a, **k):
        raise exc

    monkeypatch.setattr("modules.gemini_handler.analyser_texte", boom)
    r = c.post("/api/chat/conversations/%d/messages" % cid, json={"message": "bonjour"})
    assert r.status_code == code
    assert "error" in r.get_json()
    conv = c.get("/api/chat/conversations/%d" % cid).get_json()
    assert (conv.get("messages") or []) == []
