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
