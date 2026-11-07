import os
import json
import base64
from pathlib import Path
from flask import (Flask, render_template, request,
                   jsonify, redirect, url_for)

from config import INPUT_DIR, OUTPUT_DIR
from modules.database import (init_db, save_session, save_cards,
                               get_due_cards, update_card,
                               record_review, get_stats,
                               get_maitrise_par_sujet)
from modules.spacedrepetition import sm2
from modules.generator import (generer, generer_avec_plan,
                               proposer_plan, generer_section)

app = Flask(__name__)

@app.context_processor
def _inject_modele():
    import config
    return {"modele_ia": config.MODEL_FAST}
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB max upload

# Init DB au démarrage
init_db()
from modules.chat_db import init_chat_db
from modules.chat_routes import bp as chat_bp
init_chat_db()
app.register_blueprint(chat_bp)
os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# Pages
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    stats  = get_stats()
    sujets = get_maitrise_par_sujet()
    return render_template("index.html", stats=stats, sujets=sujets)


@app.route("/apprendre")
def apprendre():
    return render_template("apprendre.html")


@app.route("/discuter")
def discuter():
    return render_template("discuter.html")


@app.route("/revision")
def revision():
    dues = get_due_cards(limit=30)
    return render_template("revision.html", dues=dues)


@app.route("/stats")
def stats():
    sujets       = get_maitrise_par_sujet()
    global_stats = get_stats()
    return render_template("stats.html",
                           sujets=sujets,
                           global_stats=global_stats)


# ─────────────────────────────────────────────────────────────────────────────
# API — Generation Gemini
# ─────────────────────────────────────────────────────────────────────────────

import tempfile
import logging
from contextlib import contextmanager

MODES_API = {3, 4, 9}


def _erreur(e):
    """429/503 Gemini -> meme code + message clair ; reste -> 500 journalise."""
    code = getattr(e, "code", None)
    if code in (429, 503):
        logging.warning("Gemini indisponible apres retries: %s", code)
        msg = ("Quota Gemini atteint, reessaie plus tard" if code == 429
               else "Gemini est surcharge, reessaie dans un moment")
        return jsonify({"error": msg}), code
    logging.exception("Erreur route API")
    return jsonify({"error": str(e)}), 500


@contextmanager
def _img_temp(octets, ext="jpg"):
    """Fichier image temporaire unique, supprime a la sortie."""
    fd, path = tempfile.mkstemp(suffix="." + ext, dir=INPUT_DIR)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(octets)
        yield path
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


import os as _os


def _int_ou_none(v, default=None, lo=None, hi=None):
    # int borne ; None si invalide ou hors bornes
    try:
        n = int(default if v is None else v)
    except (TypeError, ValueError):
        return None
    if (lo is not None and n < lo) or (hi is not None and n > hi):
        return None
    return n


@app.context_processor
def _assets():
    def v(f):
        try:
            return int(_os.path.getmtime(_os.path.join(app.static_folder, f)))
        except OSError:
            return 0
    return {"asset_v": v}


@app.route("/api/generer", methods=["POST"])
def api_generer():
    data       = request.get_json(force=True)
    try:
        mode = int(data.get("mode", 0))
    except (TypeError, ValueError):
        mode = 0
    if mode not in MODES_API:
        return jsonify({"error": "Mode invalide"}), 400
    texte      = data.get("texte", "").strip()
    image_b64  = data.get("image_b64", "")
    contexte   = data.get("contexte", "")

    if not texte and not image_b64:
        return jsonify({"error": "Contenu vide"}), 400

    try:
        if image_b64:
            with _img_temp(base64.b64decode(image_b64)) as img_path:
                resultat = generer(img_path, mode, est_image=True, contexte=contexte)
            est_image = True
            contenu_id = "cours (image)"
        else:
            resultat  = generer(texte, mode, est_image=False, contexte=contexte)
            est_image = False
            contenu_id = texte[:60]

        # Sauvegarde SQLite pour flashcards
        if mode == 3:
            try:
                txt = resultat.strip()
                if txt.startswith("```"):
                    txt = txt.split("```")[1]
                    if txt.startswith("json"):
                        txt = txt[4:]
                cards_data = json.loads(txt)
                session_id = save_session(contenu_id, "flashcards",
                                          "image" if est_image else "text")
                save_cards(session_id, cards_data)
            except Exception as e:
                print(f"Sauvegarde SQLite : {e}")

        return jsonify({"resultat": resultat, "mode": mode})

    except Exception as e:
        return _erreur(e)


@app.route("/api/generer_plan", methods=["POST"])
def api_generer_plan():
    data      = request.get_json(force=True)
    texte     = data.get("texte", "").strip()
    plan      = data.get("plan", "").strip()
    image_b64 = data.get("image_b64", "")

    if not plan:
        return jsonify({"error": "Plan vide"}), 400

    try:
        if image_b64:
            with _img_temp(base64.b64decode(image_b64)) as img_path:
                resultat = generer_avec_plan(img_path, plan, est_image=True)
        else:
            resultat = generer_avec_plan(texte, plan, est_image=False)

        return jsonify({"resultat": resultat})
    except Exception as e:
        return _erreur(e)


# ─────────────────────────────────────────────────────────────────────────────
# API — Revision espacee
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/revision/cartes", methods=["GET"])
def api_revision_cartes():
    dues = get_due_cards(limit=30)
    return jsonify({"cartes": dues, "total": len(dues)})


@app.route("/api/revision/evaluer", methods=["POST"])
def api_revision_evaluer():
    data    = request.get_json(force=True)
    card_id = _int_ou_none(data.get("card_id"))
    score   = _int_ou_none(data.get("score"))
    if card_id is None or score is None:
        return jsonify({"error": "card_id ou score invalide"}), 400

    if not (0 <= score <= 5):
        return jsonify({"error": "Score invalide (0-5)"}), 400

    dues = get_due_cards(limit=200)
    card = next((c for c in dues if c["id"] == card_id), None)

    if not card:
        return jsonify({"error": "Carte introuvable"}), 404

    updated = sm2(card, score)
    update_card(updated)
    record_review(card_id, score, updated["interval_days"])

    return jsonify({
        "interval_days": updated["interval_days"],
        "next_review":   updated["next_review"],
        "maitrisee":     score >= 3
    })


# ─────────────────────────────────────────────────────────────────────────────
# API — Stats
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/stats", methods=["GET"])
def api_stats():
    return jsonify({
        "global": get_stats(),
        "sujets": get_maitrise_par_sujet()
    })


# ─────────────────────────────────────────────────────────────────────────────
# Option C — Exposé interactif (plan + sections)
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/expose/plan", methods=["POST"])
def api_expose_plan():
    """
    Étape 1 : Gemini propose un plan JSON pour le sujet donné.
    Body : { sujet, contexte }
    """
    data          = request.get_json(force=True)
    sujet         = data.get("sujet", "").strip()
    contexte      = data.get("contexte", "").strip()
    longueur      = data.get("longueur", "complet")
    consigne_perso= data.get("consigne_perso", "").strip()

    if not sujet:
        return jsonify({"error": "Sujet vide"}), 400

    try:
        raw = proposer_plan(sujet, contexte, longueur, consigne_perso)
        # Nettoyer le JSON
        txt = raw.strip()
        if txt.startswith("```"):
            txt = txt.split("```")[1]
            if txt.startswith("json"):
                txt = txt[4:]
        plan = json.loads(txt)
        return jsonify({"plan": plan})
    except Exception as e:
        return _erreur(e)


@app.route("/api/expose/section", methods=["POST"])
def api_expose_section():
    """
    Étape 2 : Génère une section du plan.
    Body : { sujet, plan, index, contenu_precedent, texte, image_b64 }
    """
    data              = request.get_json(force=True)
    sujet             = data.get("sujet", "").strip()
    plan              = data.get("plan", [])
    index             = _int_ou_none(data.get("index", 0), 0, 0, 200)
    if index is None:
        return jsonify({"error": "index invalide"}), 400
    contenu_precedent = data.get("contenu_precedent", "")
    texte             = data.get("texte", "").strip()
    image_b64         = data.get("image_b64", "")
    longueur          = data.get("longueur", "complet")
    consigne_perso    = data.get("consigne_perso", "").strip()

    if not plan:
        return jsonify({"error": "Plan vide"}), 400

    try:
        if image_b64:
            with _img_temp(base64.b64decode(image_b64)) as img_path:
                resultat = generer_section(
                    sujet, plan, index, contenu_precedent,
                    est_image=True, contenu=img_path,
                    longueur=longueur, consigne_perso=consigne_perso
                )
        else:
            resultat = generer_section(
                sujet, plan, index, contenu_precedent,
                est_image=False, contenu=texte,
                longueur=longueur, consigne_perso=consigne_perso
            )
        return jsonify({"section": resultat, "index": index})
    except Exception as e:
        return _erreur(e)


# ─────────────────────────────────────────────────────────────────────────────
# Test auto-évaluation
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/expose/test", methods=["POST"])
def api_expose_test():
    """
    Génère 5 questions sur le contenu de l'exposé.
    Body : { contenu, sujet }
    Retourne : [{"question": "...", "reponse_attendue": "..."}]
    """
    from modules.generator import SYSTEM_PROMPT
    from modules.gemini_handler import analyser_texte

    data    = request.get_json(force=True)
    contenu = data.get("contenu", "").strip()
    sujet   = data.get("sujet", "ce sujet").strip()

    if not contenu:
        return jsonify({"error": "Contenu vide"}), 400

    prompt = f"""{SYSTEM_PROMPT}

Voici un exposé sur : {sujet}
---
{contenu[:4000]}
---

Génère exactement 5 questions de compréhension variées sur cet exposé.
Mélange : définitions, mécanismes, comparaisons, applications.

Réponds UNIQUEMENT en JSON, sans texte avant ou après :
[
  {{"question": "...", "reponse_attendue": "Réponse complète en 2-3 phrases."}},
  ...
]"""

    try:
        raw = analyser_texte(contenu[:4000], prompt)
        txt = raw.strip()
        if txt.startswith("```"):
            txt = txt.split("```")[1]
            if txt.startswith("json"):
                txt = txt[4:]
        questions = json.loads(txt)
        return jsonify({"questions": questions})
    except Exception as e:
        return _erreur(e)


@app.route("/api/expose/corriger", methods=["POST"])
def api_expose_corriger():
    """
    Évalue la réponse de l'utilisateur vs la réponse attendue.
    Body : { question, reponse_user, reponse_attendue }
    Retourne : { score: 0-2, feedback: "..." }
    """
    from modules.generator import SYSTEM_PROMPT
    from modules.gemini_handler import analyser_texte

    data             = request.get_json(force=True)
    question         = data.get("question", "")
    reponse_user     = data.get("reponse_user", "").strip()
    reponse_attendue = data.get("reponse_attendue", "")

    if not reponse_user:
        return jsonify({"score": 0, "feedback": "Aucune réponse fournie."}), 200

    prompt = f"""Question : {question}

Réponse attendue : {reponse_attendue}

Réponse de l'étudiant : {reponse_user}

Évalue cette réponse sur 2 points :
- 2 = correct et complet
- 1 = partiellement correct
- 0 = incorrect ou hors sujet

Réponds UNIQUEMENT en JSON :
{{"score": 0, "feedback": "Explication courte en 1-2 phrases en français."}}"""

    try:
        raw = analyser_texte(reponse_user, prompt)
        txt = raw.strip()
        if txt.startswith("```"):
            txt = txt.split("```")[1]
            if txt.startswith("json"):
                txt = txt[4:]
        result = json.loads(txt)
        return jsonify(result)
    except Exception as e:
        return jsonify({"score": 0, "feedback": str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# Export PDF
# ─────────────────────────────────────────────────────────────────────────────

from modules.exporters.pdf import (_PDF_MODELES, generer_pdf_flashcards_bytes, pdf_moderne)





@app.route("/api/export/pdf", methods=["POST"])
def api_export_pdf():
    from flask import send_file
    import io
    data   = request.get_json(force=True)
    texte  = data.get("texte", "")
    titre  = data.get("titre", "Study Agent")
    modele = data.get("modele", "moderne")

    fn = _PDF_MODELES.get(modele, pdf_moderne)
    try:
        pdf_bytes = fn(texte, titre)
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"{titre.replace(' ','_')}_{modele}.pdf"
        )
    except Exception as e:
        return _erreur(e)


@app.route("/api/export/flashcards", methods=["POST"])
def api_export_flashcards():
    from flask import send_file
    import io
    data   = request.get_json(force=True)
    cards  = data.get("cards", [])
    titre  = data.get("titre", "Flashcards")
    try:
        pdf_bytes = generer_pdf_flashcards_bytes(cards, titre)
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"flashcards_{titre.replace(' ','_')}.pdf"
        )
    except Exception as e:
        return _erreur(e)


# ─────────────────────────────────────────────────────────────────────────────
# Import cours perso → flashcards SQLite
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/cours/importer", methods=["POST"])
def api_cours_importer():
    from modules.gemini_handler import analyser_texte, analyser_image
    import re

    data         = request.get_json(force=True)
    sujet        = data.get("sujet", "Mon cours").strip()
    nb           = _int_ou_none(data.get("nb", 10), 10, 1, 30)
    if nb is None:
        return jsonify({"error": "nb invalide (1-30)"}), 400
    texte        = data.get("texte", "").strip()
    fichier_b64  = data.get("fichier_b64", "")
    fichier_type = data.get("fichier_type", "")
    fichier_nom  = data.get("fichier_nom", "")

    prompt_fin = f"""À partir de ce cours, génère exactement {nb} flashcards pertinentes.
Réponds UNIQUEMENT avec un tableau JSON valide, sans texte avant ni après :
[{{"question": "...", "reponse": "..."}}, ...]"""

    try:
        if fichier_b64:
            fichier_bytes = base64.b64decode(fichier_b64)

            if fichier_type == "application/pdf":
                # Extraire le texte du PDF puis analyser
                import io
                try:
                    import pypdf
                    reader = pypdf.PdfReader(io.BytesIO(fichier_bytes))
                    texte_pdf = "\n".join(p.extract_text() or "" for p in reader.pages)
                except ImportError:
                    try:
                        import PyPDF2
                        reader = PyPDF2.PdfReader(io.BytesIO(fichier_bytes))
                        texte_pdf = "\n".join(p.extract_text() or "" for p in reader.pages)
                    except ImportError:
                        return jsonify({"error": "pypdf non installé. Installe-le : pip install pypdf"}), 500
                prompt = f"{prompt_fin}\n\nContenu du PDF :\n{texte_pdf[:6000]}"
                raw = analyser_texte(texte_pdf[:6000], prompt)
            else:
                # Image — sauvegarder et envoyer à Gemini Vision
                ext = fichier_nom.rsplit(".", 1)[-1].lower() if "." in fichier_nom else "jpg"
                if ext not in {"jpg", "jpeg", "png", "webp"}:
                    ext = "jpg"
                prompt = f"Voici une image de cours. {prompt_fin}"
                from modules.generator import generer
                with _img_temp(fichier_bytes, ext) as img_path:
                    raw = generer(img_path, mode=1, est_image=True, contexte=prompt)
        elif texte:
            prompt = f"{prompt_fin}\n\nCours :\n{texte[:6000]}"
            raw = analyser_texte(texte[:6000], prompt)
        else:
            return jsonify({"error": "Aucun contenu fourni"}), 400

        txt = raw.strip()
        if txt.startswith("```"):
            txt = txt.split("```")[1]
            if txt.startswith("json"): txt = txt[4:]
        match = re.search(r'\[.*\]', txt, re.DOTALL)
        if not match:
            return jsonify({"error": "Parsing JSON échoué"}), 500
        cards_raw = json.loads(match.group())
        cards = [
            {"question": c.get("question", ""), "answer": c.get("reponse", c.get("answer", ""))}
            for c in cards_raw
        ]
        session_id = save_session(sujet, "flashcards", "text")
        save_cards(session_id, cards)
        return jsonify({"cards": cards, "session_id": session_id})
    except Exception as e:
        return _erreur(e)


# ─────────────────────────────────────────────────────────────────────────────
# Test optionnel après révision
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/revision/test", methods=["POST"])
def api_revision_test():
    """
    Optionnel — génère un mini-test sur les cartes révisées.
    Body : { cartes: [{question, answer, subject}] }
    Retourne : [{"question": "...", "reponse_attendue": "..."}]
    """
    from modules.gemini_handler import analyser_texte
    import re

    data   = request.get_json(force=True)
    cartes = data.get("cartes", [])

    if not cartes:
        return jsonify({"error": "Aucune carte"}), 400

    resume = "\n".join(
        f"Q: {c.get('question','')} → R: {c.get('answer', c.get('reponse',''))}"
        for c in cartes[:20]
    )

    prompt = f"""Voici des flashcards révisées :
{resume}

Génère 5 questions de test variées (reformulées, pas copiées).
Réponds UNIQUEMENT en JSON :
[{{"question": "...", "reponse_attendue": "..."}}]"""

    try:
        raw = analyser_texte(resume, prompt)
        txt = raw.strip()
        if txt.startswith("```"):
            txt = txt.split("```")[1]
            if txt.startswith("json"):
                txt = txt[4:]
        match = re.search(r'\[.*\]', txt, re.DOTALL)
        questions = json.loads(match.group()) if match else []
        return jsonify({"questions": questions})
    except Exception as e:
        return _erreur(e)


# ─────────────────────────────────────────────────────────────────────────────
# Lancement
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 55)
    print("  STUDY AGENT - Interface web")
    print("  http://localhost:81")
    print("=" * 55)
    app.run(host="127.0.0.1", port=8081, debug=False)
