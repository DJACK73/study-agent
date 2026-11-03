"""Generation PDF (modeles + flashcards). Deplace depuis app.py."""


def _build_pdf(story, buffer):
    """Helper — construit le doc et retourne les bytes."""
    from reportlab.platypus import SimpleDocTemplate
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm as _cm
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
