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
from modules.generator import (generer, generer_avec_plan, generer_conversation,
                               proposer_plan, generer_section)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB max upload

# Init DB au démarrage
init_db()
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

@app.route("/api/generer", methods=["POST"])
def api_generer():
    data       = request.get_json(force=True)
    mode       = int(data.get("mode", 1))
    texte      = data.get("texte", "").strip()
    image_b64  = data.get("image_b64", "")
    contexte   = data.get("contexte", "")

    if not texte and not image_b64:
        return jsonify({"error": "Contenu vide"}), 400

    try:
        if image_b64:
            img_data = base64.b64decode(image_b64)
            img_path = os.path.join(INPUT_DIR, "upload_temp.jpg")
            with open(img_path, "wb") as f:
                f.write(img_data)
            resultat  = generer(img_path, mode, est_image=True, contexte=contexte)
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
        return jsonify({"error": str(e)}), 500


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
            img_data = base64.b64decode(image_b64)
            img_path = os.path.join(INPUT_DIR, "upload_temp.jpg")
            with open(img_path, "wb") as f:
                f.write(img_data)
            resultat = generer_avec_plan(img_path, plan, est_image=True)
        else:
            resultat = generer_avec_plan(texte, plan, est_image=False)

        return jsonify({"resultat": resultat})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/conversation", methods=["POST"])
def api_conversation():
    data      = request.get_json(force=True)
    contenu   = data.get("contenu", "").strip()
    question  = data.get("question", "").strip()
    image_b64 = data.get("image_b64", "")

    if not question:
        return jsonify({"error": "Question vide"}), 400

    try:
        if image_b64:
            img_data = base64.b64decode(image_b64)
            img_path = os.path.join(INPUT_DIR, "upload_temp.jpg")
            with open(img_path, "wb") as f:
                f.write(img_data)
            rep = generer_conversation(img_path, question, est_image=True)
        else:
            rep = generer_conversation(contenu, question, est_image=False)

        return jsonify({"reponse": rep})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
    card_id = int(data.get("card_id"))
    score   = int(data.get("score"))

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
        return jsonify({"error": str(e)}), 500


@app.route("/api/expose/section", methods=["POST"])
def api_expose_section():
    """
    Étape 2 : Génère une section du plan.
    Body : { sujet, plan, index, contenu_precedent, texte, image_b64 }
    """
    data              = request.get_json(force=True)
    sujet             = data.get("sujet", "").strip()
    plan              = data.get("plan", [])
    index             = int(data.get("index", 0))
    contenu_precedent = data.get("contenu_precedent", "")
    texte             = data.get("texte", "").strip()
    image_b64         = data.get("image_b64", "")
    longueur          = data.get("longueur", "complet")
    consigne_perso    = data.get("consigne_perso", "").strip()

    if not plan:
        return jsonify({"error": "Plan vide"}), 400

    try:
        if image_b64:
            img_data = base64.b64decode(image_b64)
            img_path = os.path.join(INPUT_DIR, "upload_temp.jpg")
            with open(img_path, "wb") as f:
                f.write(img_data)
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
        return jsonify({"error": str(e)}), 500


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
        return jsonify({"error": str(e)}), 500


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

def _build_pdf(story, buffer):
    """Helper — construit le doc et retourne les bytes."""
    from reportlab.platypus import SimpleDocTemplate
    from reportlab.lib.pagesizes import A4
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            leftMargin=2.5*_cm, rightMargin=2.5*_cm,
                            topMargin=2.5*_cm, bottomMargin=2.5*_cm)
    doc.build(story)
    buffer.seek(0)
    return buffer.read()


def _safe(txt):
    return txt.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")


def _parse_lignes(contenu, styles_map, story, bullet_indent=15):
    """Parser commun — convertit markdown simple en éléments ReportLab."""
    from reportlab.platypus import Paragraph, Spacer
    for ligne in contenu.split("\n"):
        ligne = ligne.strip()
        if not ligne:
            story.append(Spacer(1, 5))
            continue
        s = _safe(ligne)
        if ligne.startswith("# "):
            story.append(Paragraph(s[2:], styles_map['h1']))
        elif ligne.startswith("## "):
            story.append(Paragraph(s[3:], styles_map['h2']))
        elif ligne.startswith("### "):
            story.append(Paragraph(s[4:], styles_map['h3']))
        elif ligne.startswith(("- ", "* ", "• ")):
            story.append(Paragraph("• " + s[2:], styles_map['bullet']))
        else:
            # Gras inline **texte**
            import re
            s = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', s)
            story.append(Paragraph(s, styles_map['corps']))


# ── Modèle 1 : Académique (N&B, Times, classique) ────────
def pdf_academique(contenu: str, titre: str) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import cm as _c
    from reportlab.platypus import (SimpleDocTemplate, Paragraph,
                                    Spacer, HRFlowable)
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER, TA_LEFT
    import io

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=3*_c, rightMargin=3*_c,
                            topMargin=3*_c, bottomMargin=3*_c)
    noir  = colors.black
    gris  = colors.HexColor("#444444")
    story = []
    story.append(Paragraph(_safe(titre.upper()), ParagraphStyle(
        'T', fontName='Times-Bold', fontSize=16,
        alignment=TA_CENTER, spaceAfter=6, textColor=noir)))
    story.append(HRFlowable(width="100%", thickness=0.8,
                             color=noir, spaceAfter=18))

    sm = {
        'h1':     ParagraphStyle('h1a', fontName='Times-Bold',   fontSize=14,
                                  textColor=noir, spaceBefore=16, spaceAfter=6),
        'h2':     ParagraphStyle('h2a', fontName='Times-Bold',   fontSize=12,
                                  textColor=gris, spaceBefore=12, spaceAfter=4),
        'h3':     ParagraphStyle('h3a', fontName='Times-BoldItalic', fontSize=11,
                                  textColor=gris, spaceBefore=8,  spaceAfter=3),
        'corps':  ParagraphStyle('ca',  fontName='Times-Roman',  fontSize=11,
                                  leading=17, spaceAfter=7, alignment=TA_JUSTIFY),
        'bullet': ParagraphStyle('ba',  fontName='Times-Roman',  fontSize=11,
                                  leading=15, leftIndent=18, spaceAfter=4),
    }
    _parse_lignes(contenu, sm, story)
    doc.build(story)
    buf.seek(0)
    return buf.read()


# ── Modèle 2 : Moderne (couleurs, Inter via Helvetica) ────
def pdf_moderne(contenu: str, titre: str) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.units import cm as _c
    from reportlab.platypus import (SimpleDocTemplate, Paragraph,
                                    Spacer, HRFlowable)
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER
    from reportlab.lib.pagesizes import A4
    import io

    buf    = io.BytesIO()
    violet = colors.HexColor("#6C63FF")
    clair  = colors.HexColor("#9B8FFF")
    texte  = colors.HexColor("#1a1a2e")
    doc    = SimpleDocTemplate(buf, pagesize=A4,
                               leftMargin=2.5*_c, rightMargin=2.5*_c,
                               topMargin=2.5*_c, bottomMargin=2.5*_c)
    story  = []
    story.append(Paragraph(_safe(titre.upper()), ParagraphStyle(
        'TM', fontName='Helvetica-Bold', fontSize=20,
        textColor=violet, alignment=TA_CENTER, spaceAfter=8)))
    story.append(HRFlowable(width="100%", thickness=2,
                             color=violet, spaceAfter=20))

    sm = {
        'h1':     ParagraphStyle('h1m', fontName='Helvetica-Bold',   fontSize=15,
                                  textColor=violet, spaceBefore=18, spaceAfter=6),
        'h2':     ParagraphStyle('h2m', fontName='Helvetica-Bold',   fontSize=13,
                                  textColor=clair,  spaceBefore=12, spaceAfter=4),
        'h3':     ParagraphStyle('h3m', fontName='Helvetica-BoldOblique', fontSize=11,
                                  textColor=clair,  spaceBefore=8,  spaceAfter=3),
        'corps':  ParagraphStyle('cm',  fontName='Helvetica',        fontSize=11,
                                  leading=17, spaceAfter=8, alignment=TA_JUSTIFY,
                                  textColor=texte),
        'bullet': ParagraphStyle('bm',  fontName='Helvetica',        fontSize=11,
                                  leading=15, leftIndent=16, spaceAfter=4,
                                  textColor=texte),
    }
    _parse_lignes(contenu, sm, story)
    doc.build(story)
    buf.seek(0)
    return buf.read()


# ── Modèle 3 : Médical (structure clinique, tableaux) ─────
def pdf_medical(contenu: str, titre: str) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.units import cm as _c
    from reportlab.platypus import (SimpleDocTemplate, Paragraph,
                                    Spacer, HRFlowable)
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT, TA_CENTER
    from reportlab.lib.pagesizes import A4
    import io

    buf   = io.BytesIO()
    bleu  = colors.HexColor("#003f7f")
    cyan  = colors.HexColor("#007bbd")
    vert  = colors.HexColor("#1a7a4a")
    doc   = SimpleDocTemplate(buf, pagesize=A4,
                               leftMargin=2*_c, rightMargin=2*_c,
                               topMargin=2.5*_c, bottomMargin=2*_c)
    story = []

    # Bandeau titre bleu
    from reportlab.platypus import Table, TableStyle
    titre_tbl = Table([[Paragraph(
        f'<font color="white"><b>{_safe(titre.upper())}</b></font>',
        ParagraphStyle('th', fontName='Helvetica-Bold', fontSize=15,
                       textColor=colors.white, alignment=TA_CENTER)
    )]], colWidths=[16.5*_c])
    titre_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), bleu),
        ('PADDING',    (0,0), (-1,-1), 12),
        ('ROUNDEDCORNERS', [6]),
    ]))
    story.append(titre_tbl)
    story.append(Spacer(1, 16))

    sm = {
        'h1':     ParagraphStyle('h1med', fontName='Helvetica-Bold', fontSize=13,
                                  textColor=bleu,  spaceBefore=16, spaceAfter=5,
                                  borderPad=4),
        'h2':     ParagraphStyle('h2med', fontName='Helvetica-Bold', fontSize=12,
                                  textColor=cyan,  spaceBefore=10, spaceAfter=4),
        'h3':     ParagraphStyle('h3med', fontName='Helvetica-Bold', fontSize=11,
                                  textColor=vert,  spaceBefore=8,  spaceAfter=3),
        'corps':  ParagraphStyle('cmed',  fontName='Helvetica',      fontSize=11,
                                  leading=17, spaceAfter=7, alignment=TA_JUSTIFY),
        'bullet': ParagraphStyle('bmed',  fontName='Helvetica',      fontSize=11,
                                  leading=15, leftIndent=16, spaceAfter=4),
    }
    _parse_lignes(contenu, sm, story)
    doc.build(story)
    buf.seek(0)
    return buf.read()


# ── Modèle 4 : Minimaliste (épuré, beaucoup d'espace) ─────
def pdf_minimaliste(contenu: str, titre: str) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.units import cm as _c
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_JUSTIFY
    from reportlab.lib.pagesizes import A4
    import io

    buf   = io.BytesIO()
    doc   = SimpleDocTemplate(buf, pagesize=A4,
                               leftMargin=3.5*_c, rightMargin=3.5*_c,
                               topMargin=3*_c, bottomMargin=3*_c)
    gris1 = colors.HexColor("#111111")
    gris2 = colors.HexColor("#555555")
    gris3 = colors.HexColor("#888888")
    story = []
    story.append(Paragraph(_safe(titre), ParagraphStyle(
        'Tmin', fontName='Helvetica-Bold', fontSize=22,
        textColor=gris1, spaceAfter=4)))
    story.append(Paragraph("─" * 40, ParagraphStyle(
        'sep', fontName='Helvetica', fontSize=8,
        textColor=gris3, spaceAfter=20)))

    sm = {
        'h1':     ParagraphStyle('h1min', fontName='Helvetica-Bold', fontSize=14,
                                  textColor=gris1, spaceBefore=24, spaceAfter=8),
        'h2':     ParagraphStyle('h2min', fontName='Helvetica-Bold', fontSize=12,
                                  textColor=gris2, spaceBefore=16, spaceAfter=6),
        'h3':     ParagraphStyle('h3min', fontName='Helvetica-Oblique', fontSize=11,
                                  textColor=gris2, spaceBefore=10, spaceAfter=4),
        'corps':  ParagraphStyle('cmin',  fontName='Helvetica',     fontSize=11,
                                  leading=19, spaceAfter=10, alignment=TA_JUSTIFY,
                                  textColor=gris1),
        'bullet': ParagraphStyle('bmin',  fontName='Helvetica',     fontSize=11,
                                  leading=18, leftIndent=20, spaceAfter=6,
                                  textColor=gris2),
    }
    _parse_lignes(contenu, sm, story)
    doc.build(story)
    buf.seek(0)
    return buf.read()


# ── Dispatch par modèle ───────────────────────────────────
_PDF_MODELES = {
    "academique":   pdf_academique,
    "moderne":      pdf_moderne,
    "medical":      pdf_medical,
    "minimaliste":  pdf_minimaliste,
}


def generer_pdf_bytes(contenu: str, titre: str, modele: str = "moderne") -> bytes:
    """Point d'entrée unique — délègue au bon modèle."""
    fn = _PDF_MODELES.get(modele, pdf_moderne)
    return fn(contenu, titre)


def generer_pdf_flashcards_bytes(cards: list, titre: str) -> bytes:
    """PDF recto/verso des flashcards."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Table, TableStyle
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    import io

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)

    s_titre = ParagraphStyle('t', fontName='Helvetica-Bold', fontSize=16,
                             textColor=colors.HexColor("#6C63FF"),
                             alignment=TA_CENTER, spaceAfter=16)
    s_label = ParagraphStyle('l', fontName='Helvetica-Bold', fontSize=9,
                              textColor=colors.HexColor("#9094A8"),
                              spaceAfter=4)
    s_q = ParagraphStyle('q', fontName='Helvetica-Bold', fontSize=11, leading=15)
    s_a = ParagraphStyle('a', fontName='Helvetica', fontSize=11, leading=15)

    story = []
    story.append(Paragraph(f"Flashcards — {titre}", s_titre))
    story.append(HRFlowable(width="100%", thickness=1,
                            color=colors.HexColor("#6C63FF"), spaceAfter=12))

    for i, card in enumerate(cards, 1):
        question = card.get("question", "")
        answer   = card.get("reponse") or card.get("answer", "")

        q_safe = question.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
        a_safe = answer.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

        data = [
            [Paragraph(f"Carte {i} — Question", s_label),
             Paragraph(f"Carte {i} — Réponse", s_label)],
            [Paragraph(q_safe, s_q),
             Paragraph(a_safe, s_a)],
        ]
        t = Table(data, colWidths=[8.5*cm, 8.5*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (0,-1), colors.HexColor("#1E2130")),
            ('BACKGROUND', (1,0), (1,-1), colors.HexColor("#13161E")),
            ('BOX',        (0,0), (-1,-1), 1, colors.HexColor("#6C63FF")),
            ('LINEAFTER',  (0,0), (0,-1), 1, colors.HexColor("#2A2D3E")),
            ('VALIGN',     (0,0), (-1,-1), 'TOP'),
            ('PADDING',    (0,0), (-1,-1), 10),
            ('TEXTCOLOR',  (0,0), (-1,-1), colors.HexColor("#E8EAF0")),
        ]))
        story.append(t)
        story.append(Spacer(1, 8))

    doc.build(story)
    buffer.seek(0)
    return buffer.read()


# ─────────────────────────────────────────────────────────────────────────────
# Export PDF — 4 modèles
# ─────────────────────────────────────────────────────────────────────────────

def _parse_lignes(contenu: str, titre: str, story: list, styles: dict):
    """Parse le texte markdown et ajoute les éléments au story ReportLab."""
    from reportlab.platypus import Paragraph, Spacer
    for ligne in contenu.split("\n"):
        ligne = ligne.strip()
        if not ligne:
            story.append(Spacer(1, 5))
            continue
        safe = ligne.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
        safe = safe.replace("**", "").replace("*", "")  # strip markdown bold/italic
        if ligne.startswith("# "):
            story.append(Paragraph(safe[2:], styles["h1"]))
        elif ligne.startswith("## "):
            story.append(Paragraph(safe[3:], styles["h2"]))
        elif ligne.startswith("### "):
            story.append(Paragraph(safe[4:], styles["h3"]))
        elif ligne.startswith(("- ", "* ", "• ")):
            story.append(Paragraph("• " + safe[2:], styles["bullet"]))
        else:
            story.append(Paragraph(safe, styles["corps"]))



@app.route("/api/export/pdf", methods=["POST"])
def api_export_pdf():
    from flask import send_file
    import io
    data   = request.get_json(force=True)
    texte  = data.get("texte", "")
    titre  = data.get("titre", "Study Agent")
    modele = data.get("modele", "moderne")

    fn = PDF_MODELES.get(modele, pdf_moderne)
    try:
        pdf_bytes = fn(texte, titre)
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"{titre.replace(' ','_')}_{modele}.pdf"
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# Import cours perso → flashcards SQLite
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/cours/importer", methods=["POST"])
def api_cours_importer():
    from modules.gemini_handler import analyser_texte, analyser_image
    import re

    data         = request.get_json(force=True)
    sujet        = data.get("sujet", "Mon cours").strip()
    nb           = int(data.get("nb", 10))
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
                img_path = os.path.join(INPUT_DIR, f"cours_upload.{ext}")
                with open(img_path, "wb") as f:
                    f.write(fichier_bytes)
                prompt = f"Voici une image de cours. {prompt_fin}"
                # Utiliser generer() mode image comme dans api_generer
                from modules.generator import generer
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
        return jsonify({"error": str(e)}), 500


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
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# Lancement
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 55)
    print("  STUDY AGENT - Interface web")
    print("  http://localhost:81")
    print("=" * 55)
    app.run(host="0.0.0.0", port=81, debug=False)
