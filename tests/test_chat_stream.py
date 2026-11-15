import json
import pytest


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    monkeypatch.setattr("modules.database.DB_PATH", tmp_path / "t.db")
    import app as appmod
    from modules.database import init_db
    from modules.chat_db import init_chat_db
    init_db()
    init_chat_db()
    return appmod.app.test_client()


def _flux(ctx, cid, msg="Définis le paludisme"):
    r = ctx.post(f"/api/chat/conversations/{cid}/messages", json={"message": msg, "web": False, "stream": True})
    assert r.mimetype == "application/x-ndjson"
    return [json.loads(l) for l in r.get_data(as_text=True).splitlines() if l.strip()]


def test_marqueur_coupe_entre_deux_morceaux(ctx, monkeypatch):
    from modules import chat_db
    monkeypatch.setattr("modules.gemini_handler.analyser_texte_flux",
                        lambda t, p, m=None, thinking=None: iter(["Intro.\n\n[[im", "g: stomach diagram]]\n\nSuite."]))
    cid = chat_db.creer()
    lignes = _flux(ctx, cid)
    fin = lignes[-1]["fin"]
    assert "[[" not in fin["reponse"]
    assert fin["slots"] == [{"q": "stomach diagram", "apres": 0}]
    ai = [m for m in chat_db.lire(cid)["messages"] if m["role"] == "ai"]
    assert len(ai) == 1 and "[[" not in ai[0]["contenu"]


def test_erreur_avant_premier_morceau(ctx, monkeypatch):
    from modules import chat_db

    def boom(t, p, m=None, thinking=None):
        raise TimeoutError("x")
        yield

    monkeypatch.setattr("modules.gemini_handler.analyser_texte_flux", boom)
    cid = chat_db.creer()
    lignes = _flux(ctx, cid)
    assert "erreur" in lignes[-1]
    assert chat_db.lire(cid)["messages"] == []


def test_flux_vide(ctx, monkeypatch):
    from modules import chat_db
    monkeypatch.setattr("modules.gemini_handler.analyser_texte_flux", lambda t, p, m=None, thinking=None: iter([]))
    cid = chat_db.creer()
    assert "erreur" in _flux(ctx, cid)[-1]
    assert chat_db.lire(cid)["messages"] == []
