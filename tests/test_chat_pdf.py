import sqlite3
import pytest
from flask import Flask


@pytest.fixture
def cli(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    monkeypatch.setattr("modules.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("modules.chat_intent._LOG", str(tmp_path / "log.jsonl"))
    monkeypatch.setattr("modules.chat_routes.PDF_DIR", tmp_path / "pdfs")
    monkeypatch.setattr("modules.chat_routes.UPLOAD_DIR", tmp_path / "up")
    from modules import chat_db
    from modules.chat_routes import bp
    chat_db.init_chat_db()
    a = Flask(__name__)
    a.register_blueprint(bp)
    return a.test_client()


def test_migration_ajoute_pdf_path(tmp_path, monkeypatch):
    db = tmp_path / "old.db"
    c = sqlite3.connect(db)
    c.executescript(
        "CREATE TABLE conversations(id INTEGER PRIMARY KEY AUTOINCREMENT, titre TEXT NOT NULL DEFAULT 'x',"
        " created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP);"
        "CREATE TABLE messages(id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id INTEGER NOT NULL,"
        " role TEXT NOT NULL, contenu TEXT NOT NULL, sources_json TEXT, image_path TEXT,"
        " created_at DATETIME DEFAULT CURRENT_TIMESTAMP);")
    c.close()
    monkeypatch.setattr("modules.database.DB_PATH", db)
    from modules import chat_db
    chat_db.init_chat_db()
    chat_db.init_chat_db()  # idempotent
    cols = [r[1] for r in sqlite3.connect(db).execute("PRAGMA table_info(messages)")]
    assert "pdf_path" in cols


def test_get_pdf(cli, tmp_path):
    (tmp_path / "pdfs").mkdir()
    nom = "a" * 32 + ".pdf"
    (tmp_path / "pdfs" / nom).write_bytes(b"%PDF-1.4 x")
    r = cli.get(f"/api/chat/pdf/{nom}")
    assert r.status_code == 200 and r.data.startswith(b"%PDF")
    for mauvais in ("secret.txt", "A" * 32 + ".pdf", "a" * 31 + ".pdf", "b" * 32 + ".pdf"):
        assert cli.get(f"/api/chat/pdf/{mauvais}").status_code == 404


def test_delete_purge_pdf(cli, tmp_path):
    from modules import chat_db
    (tmp_path / "pdfs").mkdir()
    f = tmp_path / "pdfs" / ("b" * 32 + ".pdf")
    f.write_bytes(b"%PDF")
    cid = chat_db.creer()
    chat_db.ajouter_message(cid, "ai", "x", pdf_path=f"pdfs/{f.name}")
    assert cli.delete(f"/api/chat/conversations/{cid}").status_code == 200
    assert not f.exists()


def test_delete_global_purge_pdf(cli, tmp_path):
    from modules import chat_db
    (tmp_path / "pdfs").mkdir()
    f = tmp_path / "pdfs" / ("c" * 32 + ".pdf")
    f.write_bytes(b"%PDF")
    cid = chat_db.creer()
    chat_db.ajouter_message(cid, "ai", "x", pdf_path=f"pdfs/{f.name}")
    assert cli.delete("/api/chat/conversations?confirm=oui").status_code == 200
    assert not f.exists()


def _envoyer(cli, cid, msg):
    return cli.post(f"/api/chat/conversations/{cid}/messages", json={"message": msg})


def _conv(cli):
    return cli.post("/api/chat/conversations").get_json()["id"]


@pytest.fixture
def gem(monkeypatch):
    appels = []

    def fake(texte, prompt):
        appels.append(texte)
        return "## Cause\nPlasmodium\n\n## Traitement\nArtésunate"
    monkeypatch.setattr("modules.gemini_handler.analyser_texte", fake)
    return appels


def test_pdf_dernier_message(cli, gem, tmp_path):
    import pathlib
    cid = _conv(cli)
    _envoyer(cli, cid, "Définis le paludisme")
    d = _envoyer(cli, cid, "Fais-moi la leçon en PDF").get_json()
    assert d["pdf_path"].startswith("pdfs/") and len(gem) == 1
    assert (tmp_path / "pdfs" / pathlib.Path(d["pdf_path"]).name).read_bytes().startswith(b"%PDF")


def test_pdf_partie_et_introuvable(cli, gem):
    cid = _conv(cli)
    _envoyer(cli, cid, "Définis le paludisme")
    assert _envoyer(cli, cid, "Je veux un pdf de la partie traitement").get_json()["pdf_path"]
    d = _envoyer(cli, cid, "pdf de la partie zzzz").get_json()
    assert d["pdf_path"] and "introuvable" in d["reponse"]


def test_pdf_sujet_sans_reponse_prealable(cli, gem):
    cid = _conv(cli)
    d = _envoyer(cli, cid, "exposé en PDF sur le paludisme").get_json()
    assert d["pdf_path"] and len(gem) == 1


def test_pdf_rien_a_exporter(cli, gem):
    d = _envoyer(cli, _conv(cli), "pdf").get_json()
    assert d["pdf_path"] is None and "Aucune" in d["reponse"] and gem == []


def test_pdf_sujet_gemini_echec(cli, monkeypatch):
    def boom(t, p):
        raise RuntimeError("x")
    monkeypatch.setattr("modules.gemini_handler.analyser_texte", boom)
    cid = _conv(cli)
    assert _envoyer(cli, cid, "pdf sur le tetanos").status_code == 502
    assert cli.get(f"/api/chat/conversations/{cid}").get_json()["messages"] == []


def test_demande_proche_journalisee(cli, gem, tmp_path):
    d = _envoyer(cli, _conv(cli), "Peux-tu l'imprimer ?").get_json()
    assert d["pdf_path"] is None and (tmp_path / "log.jsonl").exists()
