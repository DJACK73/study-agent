import os
os.environ.setdefault("GEMINI_API_KEY", "dummy")
from modules.chat_routes import _reponses_ia, _titre_pdf, _MSG_RIEN


def _m(role, contenu, pdf=None):
    return {"role": role, "contenu": contenu, "pdf_path": pdf}


def test_reponses_ia_exclut_pdf_et_rien():
    msgs = [_m("user", "q"), _m("ai", "Leçon"), _m("ai", "PDF prêt : X", "pdfs/a.pdf"),
            _m("ai", _MSG_RIEN), _m("ai", "Partie « Y » introuvable : PDF du dernier message. PDF prêt : Z", "pdfs/b.pdf")]
    assert _reponses_ia(msgs) == ["Leçon"]


def test_reponses_ia_vide():
    assert _reponses_ia([_m("user", "q")]) == []


def test_titre_premier_heading():
    assert _titre_pdf("intro\n## **Paludisme** : bases\n# Autre", None, "Conv") == "Paludisme : bases"


def test_titre_repli_conversation():
    assert _titre_pdf("texte sans titre", None, "Ma conv") == "Ma conv"


def test_titre_sujet_prioritaire_et_tronque():
    assert _titre_pdf("# H", "S" * 80, "C") == "S" * 60


def test_titre_accepte_h3():
    assert _titre_pdf("### Paludisme\ntexte", None, "Conv") == "Paludisme"


def test_titre_ignore_h4():
    assert _titre_pdf("#### Détail", None, "Conv") == "Conv"
