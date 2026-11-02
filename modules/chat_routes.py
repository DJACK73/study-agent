import json
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


@bp.post("/conversations/<int:cid>/messages")
def envoyer(cid):
    from modules.gemini_handler import analyser_texte  # import local : client créé à l'import
    conv = chat_db.lire(cid)
    if conv is None:
        return jsonify({"error": "Introuvable"}), 404
    msg = ((request.get_json(silent=True) or {}).get("message") or "").strip()
    if not msg:
        return jsonify({"error": "Message vide"}), 400
    web = bool((request.get_json(silent=True) or {}).get("web"))
    texte = f"{_historique(conv['messages'])}\n\nÉtudiant : {msg}".strip()
    sources, web_statut = [], None
    if web:
        from modules.web_context import enrichir
        texte, sources, web_statut = enrichir(msg[:200], texte, medical=True)
    try:
        rep = analyser_texte(texte, CHAT_PROMPT)
    except Exception as e:
        print(f"chat gemini: {e}")
        return jsonify({"error": "Gemini indisponible"}), 502
    chat_db.ajouter_message(cid, "user", msg)
    mid = chat_db.ajouter_message(cid, "ai", rep, sources_json=(json.dumps(sources, ensure_ascii=False) if sources else None))
    titre = conv["titre"]
    if not conv["messages"] and titre == "Nouvelle discussion":
        titre = msg[:50]
        chat_db.renommer(cid, titre)
    return jsonify({"reponse": rep, "message_id": mid, "titre": titre, "sources": sources, "web_statut": web_statut})
