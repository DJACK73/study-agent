from modules.chat_intent import detecter_pdf, extraire_partie, sujet_dans


def test_sans_pdf():
    assert detecter_pdf("explique le paludisme") is None


def test_imprimable():
    assert detecter_pdf("donne-moi une version imprimable") is not None


def test_sans_partie():
    base = {"portee": "dernier", "partie": None, "sujet": None}
    assert detecter_pdf("donne la leçon en PDF") == base
    assert detecter_pdf("exposé en pdf") == base
    assert detecter_pdf("fais un pdf de la leçon") == base


def test_tout():
    assert detecter_pdf("fais un pdf de toute la discussion")["portee"] == "tout"


def test_partie():
    assert detecter_pdf("fais un PDF avec la partie traitement")["partie"] == "traitement"
    assert detecter_pdf("pdf de la section sur la prévention en pdf")["partie"] == "prevention"
    assert detecter_pdf("pdf de la partie lactation")["partie"] == "lactation"


def test_sujet():
    assert detecter_pdf("exposé en pdf sur le paludisme")["sujet"] == "le paludisme"
    assert detecter_pdf("fais un exposé sur la drépanocytose en PDF")["sujet"] == "la drepanocytose"


def test_sujet_dans():
    assert sujet_dans("Le paludisme est une maladie", "le paludisme")
    assert not sujet_dans("La drépanocytose", "le paludisme")


def test_extraire():
    md = "# Cours\n## Définition\nA\n## Traitement\nB\n### Détail\nC\n## Prévention\nD"
    assert extraire_partie(md, "traitement") == "## Traitement\nB\n### Détail\nC"
    assert extraire_partie(md, "inconnu") is None
