import os
os.environ.setdefault("GEMINI_API_KEY", "dummy")
import pytest

NOM = "a" * 32 + ".jpg"


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    monkeypatch.setattr("modules.chat_routes.UPLOAD_DIR", tmp_path)
    import app as appmod
    return appmod.app.test_client(), tmp_path


def test_img_ok(ctx):
    c, d = ctx
    (d / NOM).write_bytes(b"\xff\xd8\xff\xe0xx")
    r = c.get(f"/api/chat/img/{NOM}")
    assert r.status_code == 200 and r.mimetype == "image/jpeg"


def test_img_nom_invalide(ctx):
    c, _ = ctx
    assert c.get("/api/chat/img/..%2Fsessions.db").status_code == 404
    assert c.get("/api/chat/img/abc.jpg").status_code == 404


def test_img_absente(ctx):
    c, _ = ctx
    assert c.get(f"/api/chat/img/{NOM}").status_code == 404
