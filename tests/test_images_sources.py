import json
import pytest
from modules import images_sources as isrc


class R:
    def __init__(self, code, data=None):
        self.status_code, self._d, self.headers = code, data or {}, {}

    def json(self):
        return self._d


def _img(page, url="https://img.example/x.png", titre="Schema"):
    return {"imageUrl": url, "thumbnailUrl": url + "?t", "link": page, "title": titre}


@pytest.fixture(autouse=True)
def propre(monkeypatch, tmp_path):
    isrc._CACHE.clear()
    monkeypatch.setattr(isrc, "_pools", {})
    monkeypatch.setattr(isrc, "_USAGE", tmp_path / "u.json")
    monkeypatch.setattr(isrc, "_ACTIF", True)
    yield
    isrc._CACHE.clear()


def test_serper_domaines_exclus(monkeypatch):
    monkeypatch.setattr(isrc.config, "SERPER_API_KEYS", ["k"])
    rep = {"images": [_img("https://in.pinterest.com/p"), _img("https://commons.wikimedia.org/wiki/File:A.svg"),
                      _img("https://www.fiches-ide.fr/digestif", titre="Appareil digestif")]}
    monkeypatch.setattr(isrc.requests, "post", lambda *a, **k: R(200, rep))
    res = isrc.serper("digestive system")
    assert [x["auteur"] for x in res] == ["www.fiches-ide.fr"]
    assert res[0]["source"] == "serper" and "non" in res[0]["licence"]


def test_serper_rotation_sur_429(monkeypatch):
    monkeypatch.setattr(isrc.config, "SERPER_API_KEYS", ["k1", "k2"])
    vus = []

    def faux_post(url, headers=None, json=None, timeout=None):
        vus.append(headers["X-API-KEY"])
        if headers["X-API-KEY"] == "k1":
            return R(429)
        return R(200, {"images": [_img("https://www.fiches-ide.fr/a")]})
    monkeypatch.setattr(isrc.requests, "post", faux_post)
    assert len(isrc.serper("q1")) == 1 and vus == ["k1", "k2"]
    isrc.serper("q2")
    assert vus[2:] == ["k2"]  # k1 est en pause


def test_serper_plafond_atteint(monkeypatch):
    monkeypatch.setattr(isrc.config, "SERPER_API_KEYS", ["k"])
    monkeypatch.setattr(isrc, "_SERPER_MAX", 3)
    isrc._USAGE.write_text(json.dumps({"n": 3}), encoding="utf-8")

    def interdit(*a, **k):
        raise AssertionError("appel apres le plafond")
    monkeypatch.setattr(isrc.requests, "post", interdit)
    assert isrc.serper("q") == []


def test_serper_compteur_et_cache(monkeypatch):
    monkeypatch.setattr(isrc.config, "SERPER_API_KEYS", ["k"])
    appels = []

    def faux_post(*a, **k):
        appels.append(1)
        return R(200, {"images": [_img("https://www.fiches-ide.fr/a")]})
    monkeypatch.setattr(isrc.requests, "post", faux_post)
    isrc.serper("q")
    isrc.serper("q")
    assert len(appels) == 1
    assert json.loads(isrc._USAGE.read_text(encoding="utf-8"))["n"] == 1


def test_pixabay_ecarte_les_images_ia(monkeypatch):
    monkeypatch.setattr(isrc.config, "PIXABAY_API_KEYS", ["k"])
    hits = [{"tags": "ai généré, anatomie, corps", "webformatURL": "https://p/1.jpg", "pageURL": "https://pixabay.com/1", "user": "u1"},
            {"tags": "digestive, system, labelled, diagram", "webformatURL": "https://p/2.jpg", "pageURL": "https://pixabay.com/2", "user": "u2"}]
    monkeypatch.setattr(isrc.requests, "get", lambda *a, **k: R(200, {"hits": hits}))
    res = isrc.pixabay("digestive system")
    assert [x["page"] for x in res] == ["https://pixabay.com/2"]
    assert res[0]["licence"] == "Licence Pixabay"


def test_pixabay_erreur_non_mise_en_cache(monkeypatch):
    monkeypatch.setattr(isrc.config, "PIXABAY_API_KEYS", ["k"])
    monkeypatch.setattr(isrc.requests, "get", lambda *a, **k: R(500))
    assert isrc.pixabay("q") == [] and not isrc._CACHE


def test_complements_serper_puis_pixabay(monkeypatch):
    monkeypatch.setattr(isrc, "serper", lambda q, n=6: [{"page": "s1"}])
    monkeypatch.setattr(isrc, "pixabay", lambda q, n=6: [{"page": "p1"}, {"page": "p2"}])
    assert [x["page"] for x in isrc.complements("q", {"deja"}, 2)] == ["s1", "p1"]
    assert [x["page"] for x in isrc.complements("q", {"s1"}, 3)] == ["p1", "p2"]


def test_sans_cle_ou_desactive_rien_ne_sort(monkeypatch):
    monkeypatch.setattr(isrc.config, "SERPER_API_KEYS", [])
    monkeypatch.setattr(isrc.config, "PIXABAY_API_KEYS", [])
    assert isrc.complements("q", set(), 3) == []
    monkeypatch.setattr(isrc, "_ACTIF", False)
    monkeypatch.setattr(isrc, "serper", lambda q, n=6: [{"page": "p"}])
    assert isrc.complements("q", set(), 3) == []


def test_vider_caches():
    isrc._mettre("serper", "q", [{"page": "p"}])
    assert isrc.vider_caches() >= 1 and not isrc._CACHE
