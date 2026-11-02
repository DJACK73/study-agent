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
