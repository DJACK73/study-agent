import json
import pytest
from modules import chat_routes


class Rep:
    def __init__(self, ctype="image/jpeg", data=b"abc"):
        self.headers, self.content, self.status_code = {"content-type": ctype}, data, 200

    def raise_for_status(self):
        pass


def _commons(n):
    return [{"url": f"https://upload.wikimedia.org/{i}.png",
             "page": f"https://commons.wikimedia.org/wiki/File:Digestive_{i}.png",
             "titre": "Digestive system", "auteur": "a", "licence": "CC0"} for i in range(n)]


SERPER = {"url": "https://s.example/x.png", "vignette": "https://s.example/t.png",
          "page": "https://www.fiches-ide.fr/digestive", "titre": "Digestive system",
          "auteur": "www.fiches-ide.fr", "licence": "Licence non vérifiée", "source": "serper"}


@pytest.fixture
def faux(monkeypatch):
    monkeypatch.setattr("modules.commons.chercher_images_exa", lambda q, n=6: [])
    vus = []
    monkeypatch.setattr(chat_routes, "_vision_choix", lambda cands, contenu: vus.append(cands) or [0] * len(cands))
    return vus


def test_complements_si_peu_de_candidats(monkeypatch, faux):
    monkeypatch.setattr("modules.commons.chercher_images", lambda q, n=12: _commons(1))
    monkeypatch.setattr("modules.images_sources.complements", lambda q, deja, k: [dict(SERPER)])
    chat_routes._choisir_images([("digestive system", 3)], "contenu")
    pages = [x["page"] for x in faux[0][0][2]]
    assert len(pages) == 2 and SERPER["page"] in pages


def test_pas_de_complements_si_commons_suffit(monkeypatch, faux):
    monkeypatch.setattr("modules.commons.chercher_images", lambda q, n=12: _commons(3))
    appels = []
    monkeypatch.setattr("modules.images_sources.complements", lambda *a, **k: appels.append(1) or [])
    chat_routes._choisir_images([("digestive system", 3)], "contenu")
    assert appels == [] and len(faux[0][0][2]) == 3


def test_complement_hors_sujet_ecarte(monkeypatch, faux):
    monkeypatch.setattr("modules.commons.chercher_images", lambda q, n=12: _commons(1))
    hors = {**SERPER, "titre": "Recette de gateau", "page": "https://www.fiches-ide.fr/gateau"}
    monkeypatch.setattr("modules.images_sources.complements", lambda q, deja, k: [hors])
    chat_routes._choisir_images([("digestive system", 3)], "contenu")
    assert len(faux[0][0][2]) == 1


def test_copier_pixabay(monkeypatch, tmp_path):
    monkeypatch.setattr(chat_routes, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr("requests.get", lambda *a, **k: Rep())
    x = {"url": "https://cdn.pixabay.com/a.jpg", "page": "https://pixabay.com/p", "source": "pixabay"}
    res = chat_routes._copier_pixabay(x)
    nom = res["url"].rsplit("/", 1)[-1]
    assert res["url"].startswith("/api/chat/img/") and chat_routes._NOM_IMG.fullmatch(nom)
    assert (tmp_path / nom).read_bytes() == b"abc" and x["url"].startswith("https://cdn")


@pytest.mark.parametrize("rep", [Rep("text/html"), Rep("image/jpeg", b"x" * 3_000_001)])
def test_copier_pixabay_refuse(monkeypatch, tmp_path, rep):
    monkeypatch.setattr(chat_routes, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr("requests.get", lambda *a, **k: rep)
    assert chat_routes._copier_pixabay({"url": "https://cdn.pixabay.com/a"}) is None
    assert list(tmp_path.iterdir()) == []


def test_vision_repli_sur_la_vignette(monkeypatch):
    cands = [(0, "q", [{"url": "grosse", "vignette": "petite", "page": "p1"}])]
    monkeypatch.setattr(chat_routes, "_telecharger",
                        lambda u: None if u == "grosse" else (b"x", "image/png"))
    rep = json.dumps([{"i": 1, "choix": "1.1", "raison": "r"}])
    monkeypatch.setattr("modules.gemini_handler.analyser_contenus", lambda c, cfg=None: rep)
    assert chat_routes._vision_choix(cands, "contenu") == [0]
