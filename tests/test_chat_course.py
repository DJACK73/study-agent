import io
import os
os.environ.setdefault("GEMINI_API_KEY", "dummy")
import pytest
from modules import chat_db

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    monkeypatch.setattr("modules.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("modules.chat_routes.UPLOAD_DIR", tmp_path / "up")
    import app as appmod
    from modules.database import init_db
    from modules.chat_db import init_chat_db
    init_db()
    init_chat_db()
    return appmod.app.test_client(), tmp_path / "up"


def test_course_texte(ctx, monkeypatch):
    c, _ = ctx
    cid = chat_db.creer()

    def rep(t, p):
        chat_db.supprimer(cid)
        return "REP"
    monkeypatch.setattr("modules.gemini_handler.analyser_texte", rep)
    r = c.post(f"/api/chat/conversations/{cid}/messages", json={"message": "Définis le paludisme"})
    assert r.status_code == 404


def test_course_image_sans_orphelin(ctx, monkeypatch):
    c, up = ctx
    cid = chat_db.creer()

    def rep(chemin, p):
        chat_db.supprimer(cid)
        return "REP"
    monkeypatch.setattr("modules.gemini_handler.analyser_image", rep)
    r = c.post(f"/api/chat/conversations/{cid}/messages",
               data={"message": "Explique", "fichier": (io.BytesIO(JPEG), "a.jpg")},
               content_type="multipart/form-data")
    assert r.status_code == 404
    assert not list(up.glob("*"))
