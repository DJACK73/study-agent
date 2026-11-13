import json
from modules.chat_routes import _slug, _bloc_sources, _titre_pdf
from modules.exporters.pdf import generer_pdf_bytes


def _msg(role, contenu, src=None, pdf=None):
    return {"role": role, "contenu": contenu, "pdf_path": pdf,
            "sources_json": json.dumps(src) if src else None}


def test_slug_accents_limite_et_traversal():
    assert _slug("Appareil digestif : l'essentiel") == "appareil-digestif-l-essentiel"
    assert len(_slug("a" * 200)) <= 60
    assert _slug("../../etc/passwd") == "etc-passwd"
    assert _slug("") == "etude"


def test_bloc_sources_du_message_exporte():
    s = [{"titre": "Vidal", "url": "https://vidal.fr/x"}]
    ms = [_msg("ai", "Texte [1]", s), _msg("ai", "Autre sans source")]
    b = _bloc_sources(ms, "Texte [1]")
    assert "## Sources" in b and "[1] Vidal" in b and "https://vidal.fr/x" in b
    assert _bloc_sources(ms, "Autre sans source") == ""
    assert _bloc_sources(ms, "Texte [1]\n\nAutre sans source") == ""


def test_titre_pdf_prefere_le_titre_du_contenu():
    assert _titre_pdf("# Appareil digestif\ntexte", "explique l'appareil digestif", "C") == "Appareil digestif"
    assert _titre_pdf("texte", "Sujet", "C") == "Sujet"


def test_pdf_avec_sources_se_genere():
    c = "# Titre\n\nTexte [1]\n\n## Sources\n- [1] Vidal : https://vidal.fr/a?b=1&c=2"
    assert generer_pdf_bytes(c, "Appareil digestif").startswith(b"%PDF")
