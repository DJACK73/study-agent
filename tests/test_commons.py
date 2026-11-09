import os
os.environ.setdefault("GEMINI_API_KEY", "dummy")
import pytest
import requests
from modules import commons
from modules.chat_intent import detecter_image


def _page(idx, lic, url="https://upload.wikimedia.org/x/480px-a.jpg",
          page="https://commons.wikimedia.org/wiki/File:A.jpg",
          artist="<a href='x'>Jean</a> &amp; Co", mime="image/jpeg"):
    meta = {"Artist": {"value": artist}, "ObjectName": {"value": "Titre"}}
    if lic is not None:
        meta["LicenseShortName"] = {"value": lic}
    return {"title": "File:A.jpg", "index": idx,
            "imageinfo": [{"thumburl": url, "descriptionurl": page, "mime": mime, "extmetadata": meta}]}


class _Rep:
    def __init__(self, data):
        self._d = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._d


def _simule(monkeypatch, pages):
    monkeypatch.setattr(commons.requests, "get", lambda *a, **k: _Rep({"query": {"pages": pages}}))


def test_licences_filtrees(monkeypatch):
    _simule(monkeypatch, {"1": _page(1, "CC BY-SA 4.0"), "2": _page(2, "CC BY-NC 4.0"),
                          "3": _page(3, None), "4": _page(4, "CC0"), "5": _page(5, "Public domain"),
                          "6": _page(6, "CC BY-ND 2.0"), "7": _page(7, "Copyrighted free use")})
    res = commons.chercher_images("x", n=10)
    assert [r["licence"] for r in res] == ["CC BY-SA 4.0", "CC0", "Public domain"]


def test_auteur_html_nettoye(monkeypatch):
    _simule(monkeypatch, {"1": _page(1, "CC BY 4.0")})
    assert commons.chercher_images("x")[0]["auteur"] == "Jean & Co"


def test_urls_hors_wikimedia_rejetees(monkeypatch):
    _simule(monkeypatch, {"1": _page(1, "CC0", url="https://evil.example/a.jpg"),
                          "2": _page(2, "CC0", page="javascript:alert(1)"),
                          "3": _page(3, "CC0", url="http://upload.wikimedia.org/a.jpg")})
    assert commons.chercher_images("x") == []


def test_aucun_resultat(monkeypatch):
    monkeypatch.setattr(commons.requests, "get", lambda *a, **k: _Rep({"batchcomplete": ""}))
    assert commons.chercher_images("x") == []


@pytest.mark.parametrize("msg,attendu", [
    ("Montre-moi une image de l'hématie", "hématie"),
    ("je veux voir une photo de la mitochondrie, merci", "mitochondrie"),
    ("cherche une illustration du leucocyte", "leucocyte"),
    ("Explique cette image", None),
    ("montre une image de cela", None),
])
def test_detecter_image(msg, attendu):
    assert detecter_image(msg) == attendu


IMG = {"url": "https://upload.wikimedia.org/a.jpg", "page": "https://commons.wikimedia.org/wiki/File:A.jpg",
       "titre": "T", "auteur": "A", "licence": "CC0"}


def _prepare(monkeypatch):
    import app as appmod
    saved = []
    monkeypatch.setattr("modules.chat_db.lire", lambda cid: {"id": cid, "titre": "Nouvelle discussion", "messages": []})
    monkeypatch.setattr("modules.chat_db.ajouter_message", lambda *a, **k: saved.append((a, k)) or 1)
    monkeypatch.setattr("modules.chat_db.renommer", lambda *a: True)

    def _interdit(*a, **k):
        raise AssertionError("Gemini ne doit pas etre appele")
    monkeypatch.setattr("modules.gemini_handler.analyser_texte", _interdit)
    return appmod.app.test_client(), saved


def test_route_images_sans_gemini(monkeypatch):
    c, saved = _prepare(monkeypatch)
    monkeypatch.setattr("modules.commons.chercher_images", lambda s, n=3: [IMG])
    r = c.post("/api/chat/conversations/1/messages", json={"message": "Montre-moi une image de la mitochondrie"})
    assert r.status_code == 200
    d = r.get_json()
    assert d["images"] == [IMG] and "mitochondrie" in d["reponse"]
    assert saved[1][1]["images_json"]


def test_route_images_commons_injoignable(monkeypatch):
    c, saved = _prepare(monkeypatch)

    def _ko(s, n=3):
        raise requests.ConnectionError("coupe")
    monkeypatch.setattr("modules.commons.chercher_images", _ko)
    r = c.post("/api/chat/conversations/1/messages", json={"message": "Montre-moi une image de la mitochondrie"})
    assert r.status_code == 502 and saved == []


def test_hote_thumb_accepte(monkeypatch):
    _simule(monkeypatch, {"1": _page(1, "CC0", url="https://thumb.wikimedia.org/wikipedia/commons/thumb/0/0/a.png/480px-a.png")})
    assert len(commons.chercher_images("x")) == 1


from modules.chat_intent import veut_images


@pytest.mark.parametrize("msg,attendu", [
    ("c'est quoi le paludisme et montres des image", True),
    ("explique le rein en images", True),
    ("parle-moi du foie avec des photos", True),
    ("c'est quoi le paludisme", False),
    ("Explique cette image", False),
])
def test_veut_images(msg, attendu):
    assert veut_images(msg) is attendu


def test_route_reponse_gemini_plus_images(monkeypatch):
    import app as appmod
    saved, appels = [], []
    monkeypatch.setattr("modules.chat_db.lire", lambda cid: {"id": cid, "titre": "Nouvelle discussion", "messages": []})
    monkeypatch.setattr("modules.chat_db.ajouter_message", lambda *a, **k: saved.append((a, k)) or 1)
    monkeypatch.setattr("modules.chat_db.renommer", lambda *a: True)
    monkeypatch.setattr("modules.gemini_handler.analyser_texte", lambda t, p=None, *a, **k: appels.append(t) or "paludisme")
    monkeypatch.setattr("modules.commons.chercher_images", lambda s, n=3: [IMG])
    r = appmod.app.test_client().post("/api/chat/conversations/1/messages",
                                      json={"message": "c'est quoi le paludisme et montres des image"})
    assert r.status_code == 200
    d = r.get_json()
    assert d["images"] == [IMG] and d["reponse"] == "paludisme"
    assert "image" in appels[-1].lower()
    assert saved[1][1]["images_json"]
