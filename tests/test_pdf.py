import os
os.environ.setdefault("GEMINI_API_KEY", "dummy")
import app


def test_pdf_modeles():
    for m, fn in app._PDF_MODELES.items():
        assert fn("# T\n\n- p\n**g**", "Test")[:4] == b"%PDF", m
