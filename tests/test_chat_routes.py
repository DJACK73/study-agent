import json
import pytest
from modules.chat_routes import _requete_web

MSGS = [{"role": "user", "contenu": "Définis le paludisme en 1 phrase."},
        {"role": "ai", "contenu": "x"}]


def test_requete_suivi_court():
    assert _requete_web(MSGS, "Et chez l enfant ?") == \
        "Définis le paludisme en 1 phrase. Et chez l enfant ?"


def test_requete_message_long():
    long = "Explique la physiopathologie du paludisme grave chez la femme enceinte"
    assert _requete_web(MSGS, long) == long


def test_requete_conversation_vide():
    assert _requete_web([], "Et chez l enfant ?") == "Et chez l enfant ?"


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    monkeypatch.setattr("modules.database.DB_PATH", tmp_path / "t.db")
    import app as appmod
    from modules.database import init_db
    from modules.chat_db import init_chat_db
    init_db()
    init_chat_db()
    monkeypatch.setattr("modules.gemini_handler.analyser_texte", lambda t, p: "REP")
    return appmod.app.test_client()


def _post(c, cid, **body):
    return c.post(f"/api/chat/conversations/{cid}/messages", json=body)


def test_titre_auto_defaut(ctx):
    from modules import chat_db
    cid = chat_db.creer()
    r = _post(ctx, cid, message="Définis le paludisme", web=False)
    assert r.status_code == 200
    assert r.get_json()["titre"] == "Définis le paludisme"
    assert chat_db.lire(cid)["titre"] == "Définis le paludisme"


def test_titre_renomme_conserve(ctx):
    from modules import chat_db
    cid = chat_db.creer("Perso")
    assert _post(ctx, cid, message="Définis le paludisme").get_json()["titre"] == "Perso"
    assert chat_db.lire(cid)["titre"] == "Perso"


def test_sources_json_stocke(ctx, monkeypatch):
    from modules import chat_db
    src = [{"titre": "Paludisme", "date": None, "url": "https://x.org", "extrait": "e"}]
    vus = {}

    def fake(requete, texte, medical=True):
        vus["requete"] = requete
        return texte, src, "ok"

    monkeypatch.setattr("modules.web_context.enrichir", fake)
    cid = chat_db.creer()
    _post(ctx, cid, message="Définis le paludisme en 1 phrase.", web=False)
    r = _post(ctx, cid, message="Et chez l enfant ?", web=True).get_json()
    assert r["web_statut"] == "ok"
    assert vus["requete"]  # le contenu vient de Gemini : voir test_chat_pdf.py::test_web_utilise_sujet_gemini
    msgs = chat_db.lire(cid)["messages"]
    assert msgs[-1]["role"] == "ai" and json.loads(msgs[-1]["sources_json"]) == src
    assert msgs[-2]["sources_json"] is None


def test_gemini_echec_rien_sauvegarde(ctx, monkeypatch):
    from modules import chat_db

    def boom(t, p):
        raise RuntimeError("panne")

    monkeypatch.setattr("modules.gemini_handler.analyser_texte", boom)
    cid = chat_db.creer()
    assert _post(ctx, cid, message="Bonjour").status_code == 502
    assert chat_db.lire(cid)["messages"] == []


def test_cascade_epargne_revision(ctx):
    from modules import chat_db
    from modules.database import get_conn, save_session
    save_session("sujet", "mode")
    cid = chat_db.creer()
    _post(ctx, cid, message="Q")

    def n(t):
        with get_conn() as c:
            return c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]

    assert (n("messages"), n("sessions")) == (2, 1)
    assert ctx.delete(f"/api/chat/conversations/{cid}").status_code == 200
    assert (n("messages"), n("conversations"), n("sessions")) == (0, 0, 1)


def test_delete_global_exige_confirm(ctx):
    from modules import chat_db
    chat_db.creer()
    assert ctx.delete("/api/chat/conversations").status_code == 400
    assert len(chat_db.lister()) == 1
    assert ctx.delete("/api/chat/conversations?confirm=oui").status_code == 200
    assert chat_db.lister() == []


PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20


def _img(c, cid, contenu, nom="x.png", **extra):
    import io
    return c.post(f"/api/chat/conversations/{cid}/messages",
                  data={"message": "Q", "image": (io.BytesIO(contenu), nom), **extra},
                  content_type="multipart/form-data")


def test_image_valide(ctx, tmp_path, monkeypatch):
    from modules import chat_db
    monkeypatch.setattr("modules.chat_routes.UPLOAD_DIR", tmp_path / "up")
    monkeypatch.setattr("modules.gemini_handler.analyser_image", lambda p, pr: "IMG")
    cid = chat_db.creer()
    r = _img(ctx, cid, PNG, nom="../../evil.jpg")
    assert r.status_code == 200 and r.get_json()["reponse"] == "IMG"
    fichiers = list((tmp_path / "up").iterdir())
    assert len(fichiers) == 1 and fichiers[0].suffix == ".png" and "evil" not in fichiers[0].name
    m = chat_db.lire(cid)["messages"]
    assert m[0]["image_path"] == f"uploads/{fichiers[0].name}" and m[1]["image_path"] is None


def test_image_fausse_refusee(ctx, tmp_path, monkeypatch):
    from modules import chat_db
    monkeypatch.setattr("modules.chat_routes.UPLOAD_DIR", tmp_path / "up")
    cid = chat_db.creer()
    assert _img(ctx, cid, b"pas une image", nom="x.jpg").status_code == 400
    assert not (tmp_path / "up").exists() and chat_db.lire(cid)["messages"] == []


def test_image_gemini_echec_nettoie(ctx, tmp_path, monkeypatch):
    from modules import chat_db

    def boom(p, pr):
        raise RuntimeError("panne")

    monkeypatch.setattr("modules.chat_routes.UPLOAD_DIR", tmp_path / "up")
    monkeypatch.setattr("modules.gemini_handler.analyser_image", boom)
    cid = chat_db.creer()
    assert _img(ctx, cid, PNG).status_code == 502
    assert list((tmp_path / "up").iterdir()) == [] and chat_db.lire(cid)["messages"] == []


def test_delete_purge_les_images(ctx, tmp_path, monkeypatch):
    from modules import chat_db
    monkeypatch.setattr("modules.chat_routes.UPLOAD_DIR", tmp_path / "up")
    monkeypatch.setattr("modules.gemini_handler.analyser_image", lambda p, pr: "IMG")
    c1, c2 = chat_db.creer(), chat_db.creer()
    _img(ctx, c1, PNG)
    _img(ctx, c2, PNG)
    assert len(list((tmp_path / "up").iterdir())) == 2
    assert ctx.delete(f"/api/chat/conversations/{c1}").status_code == 200
    assert len(list((tmp_path / "up").iterdir())) == 1
    assert ctx.delete("/api/chat/conversations?confirm=oui").status_code == 200
    assert list((tmp_path / "up").iterdir()) == []
