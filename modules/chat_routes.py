import json
import re
import uuid
from pathlib import Path
from flask import Blueprint, jsonify, request, send_from_directory
from modules import chat_db
from modules.chat_intent import detecter_pdf, extraire_partie, journaliser_rate, sujet_dans

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
    chemins = _chemins_images(cid)
    n = chat_db.supprimer(cid)
    if n:
        _purger(chemins)
    return (jsonify({"ok": True}), 200) if n else (jsonify({"error": "Introuvable"}), 404)


@bp.delete("/conversations")
def supprime_tout():
    if request.args.get("confirm") != "oui":
        return jsonify({"error": "Ajouter ?confirm=oui"}), 400
    chemins = _chemins_images()
    n = chat_db.supprimer(None)
    _purger(chemins)
    return jsonify({"supprimees": n})


def _chemins_images(cid=None) -> list[str]:
    """Chemins relatifs des fichiers (images et PDF) rattachés aux messages."""
    from modules.database import get_conn
    out = []
    with get_conn() as conn:
        for col in ("image_path", "pdf_path"):
            sql = f"SELECT {col} FROM messages WHERE {col} IS NOT NULL"
            rows = conn.execute(sql + (" AND conversation_id=?" if cid else ""),
                                (cid,) if cid else ()).fetchall()
            out += [r[col] for r in rows]
    return out


def _purger(chemins: list[str]) -> None:
    """Supprime les fichiers après la suppression en base. Seul le nom de fichier est utilisé."""
    for rel in chemins:
        base = PDF_DIR if rel.startswith("pdfs/") else UPLOAD_DIR
        (base / Path(rel).name).unlink(missing_ok=True)


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
PDF_DIR = Path(__file__).resolve().parent.parent / "data" / "pdfs"


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
    demande = None if data else detecter_pdf(msg)
    journaliser_rate(msg, demande)
    if demande:
        return _repondre_pdf(cid, conv, msg, demande)
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
                    "web_statut": web_statut, "image_path": rel, "pdf_path": None})


_NOM_PDF = re.compile(r"[0-9a-f]{32}\.pdf")


@bp.get("/pdf/<nom>")
def telecharger_pdf(nom):
    if not _NOM_PDF.fullmatch(nom):
        return jsonify({"error": "Introuvable"}), 404
    return send_from_directory(PDF_DIR, nom, mimetype="application/pdf")


def _repondre_pdf(cid, conv, msg, d):
    """Demande de PDF : règles fixes. Gemini seulement pour un sujet sans réponse préalable."""
    from modules.exporters.pdf import generer_pdf_bytes
    from modules.gemini_handler import analyser_texte
    ias = [m["contenu"] for m in conv["messages"] if m["role"] == "ai"]
    note, contenu = "", ""
    if d["portee"] == "tout":
        contenu = "\n\n".join(ias)
    elif d["portee"] == "partie":
        contenu = next((p for p in (extraire_partie(c, d["partie"]) for c in reversed(ias)) if p), "")
        if not contenu and ias:
            contenu = ias[-1]
            note = f"Partie « {d['partie']} » introuvable : PDF du dernier message. "
    elif ias:
        contenu = ias[-1]
    sujet = d.get("sujet")
    try:
        if sujet and not (contenu and sujet_dans(contenu, sujet)):
            contenu = analyser_texte(f"Rédige un exposé structuré en Markdown sur : {sujet}", CHAT_PROMPT)
        if not contenu:
            rep, rel = "Aucune réponse à exporter pour l'instant.", None
        else:
            titre_pdf = (sujet or conv["titre"])[:60]
            PDF_DIR.mkdir(parents=True, exist_ok=True)
            fichier = PDF_DIR / f"{uuid.uuid4().hex}.pdf"
            fichier.write_bytes(generer_pdf_bytes(contenu, titre_pdf, "moderne"))
            rel, rep = f"pdfs/{fichier.name}", f"{note}PDF prêt : {titre_pdf}"
    except Exception as e:
        print(f"chat pdf: {e}")
        return jsonify({"error": "Génération PDF échouée"}), 502
    chat_db.ajouter_message(cid, "user", msg)
    mid = chat_db.ajouter_message(cid, "ai", rep, pdf_path=rel)
    titre = conv["titre"]
    if not conv["messages"] and titre == "Nouvelle discussion":
        titre = msg[:50]
        chat_db.renommer(cid, titre)
    return jsonify({"reponse": rep, "message_id": mid, "titre": titre, "sources": [],
                    "web_statut": None, "image_path": None, "pdf_path": rel})
