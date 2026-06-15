import sqlite3
from pathlib import Path
from datetime import date

DB_PATH = Path(__file__).parent.parent / "data" / "sessions.db"


# ─────────────────────────────────────────────
# Connexion
# ─────────────────────────────────────────────

def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ─────────────────────────────────────────────
# Initialisation (idempotent — safe à appeler au démarrage)
# ─────────────────────────────────────────────

def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                subject     TEXT NOT NULL,
                mode        TEXT NOT NULL,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                input_type  TEXT DEFAULT 'text'
            );

            CREATE TABLE IF NOT EXISTS cards (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id    INTEGER NOT NULL REFERENCES sessions(id),
                question      TEXT NOT NULL,
                answer        TEXT NOT NULL,
                next_review   DATE DEFAULT CURRENT_DATE,
                interval_days INTEGER DEFAULT 1,
                ease_factor   REAL DEFAULT 2.5,
                repetitions   INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS reviews (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                card_id      INTEGER NOT NULL REFERENCES cards(id),
                reviewed_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                score        INTEGER CHECK(score BETWEEN 0 AND 5),
                new_interval INTEGER
            );
        """)


# ─────────────────────────────────────────────
# Sessions
# ─────────────────────────────────────────────

def save_session(subject: str, mode: str, input_type: str = "text") -> int:
    """Crée une session et retourne son id."""
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO sessions (subject, mode, input_type) VALUES (?, ?, ?)",
            (subject, mode, input_type)
        )
        return cur.lastrowid


# ─────────────────────────────────────────────
# Cards
# ─────────────────────────────────────────────

def save_cards(session_id: int, cards: list[dict]):
    """
    Sauvegarde une liste de flashcards pour une session.
    cards = [{"question": "...", "answer": "..."}, ...]
    Accepte aussi la clé 'reponse' (format Gemini natif).
    """
    rows = []
    for c in cards:
        question = c.get("question", "").strip()
        answer = c.get("answer") or c.get("reponse", "")
        answer = str(answer).strip()
        if question and answer:
            rows.append((session_id, question, answer))

    if not rows:
        print("⚠️  Aucune carte valide à sauvegarder.")
        return

    with get_conn() as conn:
        conn.executemany(
            "INSERT INTO cards (session_id, question, answer) VALUES (?, ?, ?)",
            rows
        )
    print(f"✅  {len(rows)} carte(s) sauvegardée(s).")


def get_due_cards(limit: int = 20) -> list[dict]:
    """Retourne les cartes dues aujourd'hui ou en retard."""
    today = date.today().isoformat()
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT c.*, s.subject
            FROM cards c
            JOIN sessions s ON c.session_id = s.id
            WHERE c.next_review <= ?
            ORDER BY c.next_review ASC
            LIMIT ?
        """, (today, limit)).fetchall()
    return [dict(r) for r in rows]


def update_card(card: dict):
    """Met à jour interval, ease_factor, repetitions, next_review d'une carte."""
    with get_conn() as conn:
        conn.execute("""
            UPDATE cards
            SET interval_days = ?,
                ease_factor   = ?,
                repetitions   = ?,
                next_review   = ?
            WHERE id = ?
        """, (
            card["interval_days"],
            card["ease_factor"],
            card["repetitions"],
            card["next_review"],
            card["id"]
        ))


# ─────────────────────────────────────────────
# Reviews
# ─────────────────────────────────────────────

def record_review(card_id: int, score: int, new_interval: int):
    """Enregistre une review dans l'historique."""
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO reviews (card_id, score, new_interval) VALUES (?, ?, ?)",
            (card_id, score, new_interval)
        )


# ─────────────────────────────────────────────
# Stats (utile pour Phase 2 — score de maîtrise)
# ─────────────────────────────────────────────

def get_stats() -> dict:
    """Résumé global : sujets, cartes, cartes dues."""
    today = date.today().isoformat()
    with get_conn() as conn:
        total_cards = conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
        due_cards   = conn.execute(
            "SELECT COUNT(*) FROM cards WHERE next_review <= ?", (today,)
        ).fetchone()[0]
        subjects    = conn.execute(
            "SELECT DISTINCT subject FROM sessions ORDER BY subject"
        ).fetchall()
    return {
        "total_cards": total_cards,
        "due_today":   due_cards,
        "subjects":    [r["subject"] for r in subjects]
    }


def get_maitrise_par_sujet() -> list[dict]:
    """
    Calcule le score de maîtrise par sujet.

    Une carte est considérée maîtrisée si :
      - elle a été révisée au moins une fois (repetitions > 0)
      - ET son dernier score était >= 3

    Retourne une liste triée par score décroissant :
    [
      {
        "subject": "Drépanocytose",
        "total": 8,
        "maitrisees": 6,
        "score_pct": 75,
        "intervalle_moyen": 4,   # jours — indique la stabilité mémorielle
        "dues": 2
      },
      ...
    ]
    """
    today = date.today().isoformat()
    with get_conn() as conn:
        # Tous les sujets distincts avec leurs cartes
        sujets = conn.execute("""
            SELECT DISTINCT s.subject
            FROM sessions s
            JOIN cards c ON c.session_id = s.id
            ORDER BY s.subject
        """).fetchall()

        resultats = []
        for row in sujets:
            subject = row["subject"]

            # Total cartes pour ce sujet
            total = conn.execute("""
                SELECT COUNT(*) FROM cards c
                JOIN sessions s ON c.session_id = s.id
                WHERE s.subject = ?
            """, (subject,)).fetchone()[0]

            # Cartes maîtrisées = dernier score >= 3
            # On récupère le dernier score de chaque carte via MAX(reviewed_at)
            maitrisees = conn.execute("""
                SELECT COUNT(*) FROM (
                    SELECT r.card_id, r.score
                    FROM reviews r
                    JOIN cards c ON r.card_id = c.id
                    JOIN sessions s ON c.session_id = s.id
                    WHERE s.subject = ?
                    AND r.reviewed_at = (
                        SELECT MAX(r2.reviewed_at)
                        FROM reviews r2
                        WHERE r2.card_id = r.card_id
                    )
                    AND r.score >= 3
                )
            """, (subject,)).fetchone()[0]

            # Intervalle moyen (stabilité mémorielle)
            intervalle = conn.execute("""
                SELECT ROUND(AVG(c.interval_days), 1)
                FROM cards c
                JOIN sessions s ON c.session_id = s.id
                WHERE s.subject = ?
            """, (subject,)).fetchone()[0] or 1.0

            # Cartes encore dues
            dues = conn.execute("""
                SELECT COUNT(*) FROM cards c
                JOIN sessions s ON c.session_id = s.id
                WHERE s.subject = ? AND c.next_review <= ?
            """, (subject, today)).fetchone()[0]

            score_pct = round(maitrisees / total * 100) if total > 0 else 0

            resultats.append({
                "subject":          subject,
                "total":            total,
                "maitrisees":       maitrisees,
                "score_pct":        score_pct,
                "intervalle_moyen": intervalle,
                "dues":             dues
            })

    return sorted(resultats, key=lambda x: x["score_pct"], reverse=True)
