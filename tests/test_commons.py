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
    assert d["images"] == [] and d["reponse"] == "paludisme"
    assert d["slots"] == [{"q": "paludisme", "apres": None}]
    assert "image" in appels[-1].lower()
    assert not saved[1][1].get("images_json")


def _route_images(monkeypatch, imgs, vision):
    import app as appmod
    maj = []
    monkeypatch.setattr("modules.chat_db.lire_message", lambda mid: {"id": mid, "role": "ai", "contenu": "texte"})
    monkeypatch.setattr("modules.chat_db.maj_images", lambda mid, j: maj.append((mid, j)) or True)
    monkeypatch.setattr("modules.commons.chercher_images", lambda s, n=3: imgs)
    monkeypatch.setattr("modules.chat_routes._vision_choix", vision)
    r = appmod.app.test_client().post("/api/chat/messages/7/images",
                                      json={"slots": [{"q": "liver anatomy", "apres": 1}]})
    return r, maj


def test_images_a_la_demande_choix_par_vision(monkeypatch):
    autre = {**IMG, "titre": "autre"}
    r, maj = _route_images(monkeypatch, [IMG, autre], lambda cands, contenu: [1])
    assert r.status_code == 200 and r.get_json()["images"] == [{**autre, "apres": 1}]
    assert maj and maj[0][0] == 7


def test_images_a_la_demande_vision_rejette(monkeypatch):
    r, maj = _route_images(monkeypatch, [IMG], lambda cands, contenu: [None])
    assert r.get_json()["images"] == [] and maj == []


def test_images_a_la_demande_repli_si_vision_echoue(monkeypatch):
    def ko(cands, contenu):
        raise TimeoutError("lent")
    r, maj = _route_images(monkeypatch, [IMG], ko)
    assert r.get_json()["images"] == [{**IMG, "apres": 1}]


def test_meme_image_jamais_deux_fois(monkeypatch):
    from modules import chat_routes
    monkeypatch.setattr("modules.commons.chercher_images", lambda s, n=3: [IMG])
    monkeypatch.setattr("modules.chat_routes._vision_choix", lambda cands, contenu: [0, 0])
    out = chat_routes._choisir_images([("liver anatomy", 0), ("stomach anatomy", 1)], "texte")
    assert len(out) == 1


def test_une_seule_requete_ou_et_cache(monkeypatch):
    appels = []

    def fake(*a, **k):
        appels.append(k["params"]["gsrsearch"])
        return _Rep({"query": {"pages": {"1": _page(1, "CC0")}}})
    monkeypatch.setattr(commons.requests, "get", fake)
    commons.chercher_images("coeur")
    commons.chercher_images("coeur")
    assert len(appels) == 1 and "bitmap|drawing" in appels[0]


class _R429(_Rep):
    status_code = 429
    headers = {"Retry-After": "0"}

    def raise_for_status(self):
        raise requests.HTTPError("429")


def test_reprise_sur_429(monkeypatch):
    seq = [_R429({}), _Rep({"query": {"pages": {"1": _page(1, "CC0")}}})]
    monkeypatch.setattr(commons.requests, "get", lambda *a, **k: seq.pop(0))
    monkeypatch.setattr(commons.time, "sleep", lambda s: None)
    assert len(commons.chercher_images("foie")) == 1


def test_requete_trop_precise_reduite(monkeypatch):
    appels = []

    def fake(*a, **k):
        appels.append(k["params"]["gsrsearch"])
        if len(appels) == 1:
            return _Rep({"batchcomplete": ""})
        return _Rep({"query": {"pages": {"1": _page(1, "CC0")}}})
    monkeypatch.setattr(commons.requests, "get", fake)
    res = commons.chercher_images("esophagus and swallowing mechanism diagram")
    assert len(res) == 1 and len(appels) == 2
    assert "mechanism" not in appels[1] and "diagram" in appels[1]
