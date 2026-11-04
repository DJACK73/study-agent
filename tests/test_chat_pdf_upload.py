import io
import os
os.environ.setdefault("GEMINI_API_KEY", "dummy")
from reportlab.pdfgen import canvas
from modules.chat_routes import _texte_pdf


def _pdf(txt):
    b = io.BytesIO()
    c = canvas.Canvas(b)
    if txt:
        c.drawString(72, 800, txt)
    c.showPage()
    c.save()
    return b.getvalue()


def test_texte_extrait():
    assert "Plasmodium" in _texte_pdf(_pdf("Plasmodium falciparum"))


def test_pdf_sans_texte():
    assert _texte_pdf(_pdf("")) == ""


def test_pdf_corrompu():
    assert _texte_pdf(b"%PDF-xx") == ""


def test_plafond(monkeypatch):
    monkeypatch.setattr("modules.chat_routes.PDF_MAX_CAR", 10)
    assert len(_texte_pdf(_pdf("Plasmodium falciparum"))) == 10
