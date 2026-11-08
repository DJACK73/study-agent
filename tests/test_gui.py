import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def lire(p):
    return (ROOT / p).read_text(encoding="utf-8")


def test_sidebar_icones_svg_et_libelles_dans_span():
    html = lire("templates/base.html")
    items = re.findall(r'<a href="[^"]*" class="nav-item.*?</a>', html, re.S)
    assert len(items) == 5
    for it in items:
        assert "<svg" in it and 'class="nav-text"' in it
        assert not re.search("[\U0001F300-\U0001FAFF]", it)


def test_dashboard_sans_texte_obsolete():
    assert "11 modes" not in lire("templates/index.html")


def test_contexte_sans_exemple():
    m = re.search(r'id="contexte"[^>]*>', lire("templates/apprendre.html"))
    assert m and "Ex:" not in m.group(0)


def test_pas_de_regenerer_sur_flashcards():
    html = lire("templates/apprendre.html")
    m = re.search(r'id="result-flashcards".*?id="result-qcm"', html, re.S)
    assert m and "regenerer()" not in m.group(0)
