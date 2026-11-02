from modules.chat_intent import detecter_pdf, extraire_partie


def test_sans_pdf():
    assert detecter_pdf("explique le paludisme") is None


def test_sans_partie():
    assert detecter_pdf("donne la leçon en PDF") == {"portee": "dernier", "partie": None}
    assert detecter_pdf("exposé en pdf") == {"portee": "dernier", "partie": None}


def test_tout():
    assert detecter_pdf("fais un pdf de toute la discussion")["portee"] == "tout"


def test_partie():
    r = detecter_pdf("fais un PDF avec la partie traitement")
    assert r == {"portee": "partie", "partie": "traitement"}
    assert detecter_pdf("pdf de la section sur la prévention en pdf")["partie"] == "prevention"


def test_extraire():
    md = "# Cours\n## Définition\nA\n## Traitement\nB\n### Détail\nC\n## Prévention\nD"
    assert extraire_partie(md, "traitement") == "## Traitement\nB\n### Détail\nC"
    assert extraire_partie(md, "inconnu") is None
