import json
import uuid
from pathlib import Path
from flask import Blueprint, jsonify, request
from modules import chat_db

bp = Blueprint("chat", __name__, url_prefix="/api/chat")


@bp.get("/conversations")
def liste():
    return jsonify(chat_db.lister())


@bp.post("/conversations")
def nouvelle():
    titre = (request.get_json(silent=True) or {}).get("titre") or "Nouvelle discussion"
    return jsonify({"id": chat_db.creer(titre)}), 201


@bp.get("/conversations/<int:cid>")
def lecture(cid):
    c = chat_db.lire(cid)
    return (jsonify(c), 200) if c else (jsonify({"error": "Introuvable"}), 404)


@bp.patch("/conversations/<int:cid>")
def renomme(cid):
    titre = ((request.get_json(silent=True) or {}).get("titre") or "").strip()
    if not titre:
        return jsonify({"error": "Titre vide"}), 400
    ok = chat_db.renommer(cid, titre)
    return (jsonify({"ok": True}), 200) if ok else (jsonify({"error": "Introuvable"}), 404)


@bp.delete("/conversations/<int:cid>")
def supprime(cid):
    n = chat_db.supprimer(cid)
    return (jsonify({"ok": True}), 200) if n else (jsonify({"error": "Introuvable"}), 404)


@bp.delete("/conversations")
def supprime_tout():
    if request.args.get("confirm") != "oui":
        return jsonify({"error": "Ajouter ?confirm=oui"}), 400
    return jsonify({"supprimees": chat_db.supprimer(None)})


CHAT_PROMPT = (
    "Tu es un tuteur pour un étudiant en médecine. Réponds en français.\n"
    "Règles : pas de salutation, pas de préambule, pas d'analyse affichée. "
    "Commence directement par la réponse. Conserve accents et symboles (→ ≥ ₂ α). "
    "N'invente aucune URL ni aucun chiffre ; si tu ne sais pas, dis « je ne sais pas ». "
    "Utilise la conversation précédente comme contexte."
)
HIST_MAX_MSG = 12
HIST_MAX_CAR = 12000


def _requete_web(messages: list[dict], msg: str) -> str:
    """Message court (suivi) : on ajoute la dernière question de l'étudiant pour garder le sujet."""
    if len(msg) < 40:
        for m in reversed(messages):
            if m["role"] == "user":
                return f"{m['contenu'][:150]} {msg}"
    return msg[:200]


def _historique(messages: list[dict]) -> str:
    """12 derniers messages, plafonnés en caractères (les plus anciens sautent d'abord)."""
    out, total = [], 0
    for m in reversed(messages[-HIST_MAX_MSG:]):
        ligne = f"{'Étudiant' if m['role'] == 'user' else 'Tuteur'} : {m['contenu']}"
        total += len(ligne)
        if total > HIST_MAX_CAR:
            break
        out.append(ligne)
    return "\n\n".join(reversed(out))


UPLOAD_DIR = Path(__file__).resolve().parent.parent / "data" / "uploads"


def _ext_image(b: bytes) -> str | None:
    """Type réel par octets magiques. Le nom envoyé par le client n'est jamais utilisé."""
    if b[:3] == b"\xff\xd8\xff":
        return "jpg"
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "webp"
    return None


def _lire_requete():
    """Multipart (message, web, image) ou JSON (message, web)."""
    if request.mimetype == "multipart/form-data":
        f = request.form
        return ((f.get("message") or "").strip(),
                (f.get("web") or "").lower() in ("1", "true", "on"),
                request.files.get("image"))
    d = request.get_json(silent=True) or {}
    return (d.get("message") or "").strip(), bool(d.get("web")), None


@bp.post("/conversations/<int:cid>/messages")
def envoyer(cid):
    from modules.gemini_handler import analyser_texte, analyser_image  # import local : client créé à l'import
    conv = chat_db.lire(cid)
    if conv is None:
        return jsonify({"error": "Introuvable"}), 404
    msg, web, fichier = _lire_requete()
    data = ext = None
    if fichier:
        data = fichier.read()
        ext = _ext_image(data)
        if ext is None:
            return jsonify({"error": "Image invalide (jpg, png, webp)"}), 400
        msg = msg or "Explique cette image."
    if not msg:
        return jsonify({"error": "Message vide"}), 400
    texte = f"{_historique(conv['messages'])}\n\nÉtudiant : {msg}".strip()
    sources, web_statut = [], None
    if web:
        from modules.web_context import enrichir
        texte, sources, web_statut = enrichir(_requete_web(conv['messages'], msg), texte, medical=True)
    img_path = None
    if data:
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        img_path = UPLOAD_DIR / f"{uuid.uuid4().hex}.{ext}"
        img_path.write_bytes(data)
    try:
        if img_path:
            rep = analyser_image(str(img_path), f"{CHAT_PROMPT}\n\n{texte}")
        else:
            rep = analyser_texte(texte, CHAT_PROMPT)
    except Exception as e:
        print(f"chat gemini: {e}")
        if img_path:
            img_path.unlink(missing_ok=True)
        return jsonify({"error": "Gemini indisponible"}), 502
    rel = f"uploads/{img_path.name}" if img_path else None
    chat_db.ajouter_message(cid, "user", msg, image_path=rel)
    mid = chat_db.ajouter_message(cid, "ai", rep, sources_json=(json.dumps(sources, ensure_ascii=False) if sources else None))
    titre = conv["titre"]
    if not conv["messages"] and titre == "Nouvelle discussion":
        titre = msg[:50]
        chat_db.renommer(cid, titre)
    return jsonify({"reponse": rep, "message_id": mid, "titre": titre, "sources": sources,
                    "web_statut": web_statut, "image_path": rel})
