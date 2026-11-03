from modules.database import get_conn


def init_chat_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                titre      TEXT NOT NULL DEFAULT 'Nouvelle discussion',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS messages (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL
                                REFERENCES conversations(id) ON DELETE CASCADE,
                role            TEXT NOT NULL CHECK(role IN ('user','ai')),
                contenu         TEXT NOT NULL,
                sources_json    TEXT,
                image_path      TEXT,
                created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conversation_id);
        """)
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(messages)")}
        if "pdf_path" not in cols:
            conn.execute("ALTER TABLE messages ADD COLUMN pdf_path TEXT")


def creer(titre: str = "Nouvelle discussion") -> int:
    with get_conn() as conn:
        return conn.execute("INSERT INTO conversations (titre) VALUES (?)",
                            (titre[:80],)).lastrowid


def ajouter_message(conv_id: int, role: str, contenu: str,
                    sources_json: str | None = None, image_path: str | None = None,
                    pdf_path: str | None = None) -> int:
    with get_conn() as conn:
        mid = conn.execute(
            "INSERT INTO messages (conversation_id, role, contenu, sources_json, image_path, pdf_path) "
            "VALUES (?,?,?,?,?,?)", (conv_id, role, contenu, sources_json, image_path, pdf_path)).lastrowid
        conn.execute("UPDATE conversations SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (conv_id,))
        return mid


def lister() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT id, titre, updated_at FROM conversations "
                            "ORDER BY updated_at DESC, id DESC").fetchall()
        return [dict(r) for r in rows]


def lire(conv_id: int) -> dict | None:
    with get_conn() as conn:
        c = conn.execute("SELECT id, titre FROM conversations WHERE id=?", (conv_id,)).fetchone()
        if not c:
            return None
        m = conn.execute("SELECT id, role, contenu, sources_json, image_path, pdf_path, created_at "
                         "FROM messages WHERE conversation_id=? ORDER BY id", (conv_id,)).fetchall()
        return {**dict(c), "messages": [dict(r) for r in m]}


def renommer(conv_id: int, titre: str) -> bool:
    with get_conn() as conn:
        return conn.execute("UPDATE conversations SET titre=? WHERE id=?",
                            (titre[:80], conv_id)).rowcount > 0


def supprimer(conv_id: int | None = None) -> int:
    """conv_id=None : tout supprimer. Ne touche que conversations et messages."""
    with get_conn() as conn:
        if conv_id is None:
            return conn.execute("DELETE FROM conversations").rowcount
        return conn.execute("DELETE FROM conversations WHERE id=?", (conv_id,)).rowcount
