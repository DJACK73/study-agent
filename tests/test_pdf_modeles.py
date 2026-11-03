import io
import pytest
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph
from modules.exporters.pdf import (_build_pdf, generer_pdf_bytes,
                                   generer_pdf_flashcards_bytes)


@pytest.mark.parametrize("modele", ["academique", "moderne", "medical", "minimaliste", "inconnu"])
def test_modeles_pdf(modele):
    b = generer_pdf_bytes("# Titre\n\n- α ≥ 2\n\nTexte é à ç", "Test", modele)
    assert b.startswith(b"%PDF")


def test_flashcards_pdf():
    assert generer_pdf_flashcards_bytes([{"question": "Q?", "answer": "R"}], "T").startswith(b"%PDF")


def test_build_pdf_cm_defini():
    story = [Paragraph("x", getSampleStyleSheet()["Normal"])]
    assert _build_pdf(story, io.BytesIO()).startswith(b"%PDF")
