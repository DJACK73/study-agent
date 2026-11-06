import base64
import os
import pytest


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    monkeypatch.setattr("modules.database.DB_PATH", tmp_path / "t.db")
    import app as appmod
    from modules.database import init_db
    from modules.chat_db import init_chat_db
    init_db()
    init_chat_db()
    inp = tmp_path / "in"
    inp.mkdir()
    monkeypatch.setattr(appmod, "INPUT_DIR", str(inp))
    return appmod, appmod.app.test_client(), inp


def test_apprendre_cartes(env):
    _, c, _ = env
    r = c.get("/apprendre")
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert html.count("data-mode=") == 5
    assert 'data-mode="4"' in html
    for retire in (1, 5, 6, 7, 8):
        assert f'data-mode="{retire}"' not in html


@pytest.mark.parametrize("mode", [0, 1, 5, 8, 99, "abc", None])
def test_generer_mode_invalide(env, mode):
    _, c, _ = env
    r = c.post("/api/generer", json={"mode": mode, "texte": "x"})
    assert r.status_code == 400
    assert r.get_json()["error"] == "Mode invalide"


def test_generer_texte_ok(env, monkeypatch):
    appmod, c, _ = env
    monkeypatch.setattr(appmod, "generer", lambda *a, **k: "RES")
    r = c.post("/api/generer", json={"mode": 4, "texte": "cours"})
    assert r.status_code == 200
    d = r.get_json()
    assert d["resultat"] == "RES"
    assert "web_statut" not in d and "sources" not in d


def test_generer_image_fichier_supprime(env, monkeypatch):
    appmod, c, inp = env
    vus = []

    def faux(path, mode, est_image=False, contexte=""):
        vus.append(os.path.exists(path))
        return "RES"

    monkeypatch.setattr(appmod, "generer", faux)
    b64 = base64.b64encode(b"abc").decode()
    r = c.post("/api/generer", json={"mode": 4, "image_b64": b64})
    assert r.status_code == 200
    assert vus == [True]
    assert list(inp.iterdir()) == []


def test_img_temp_nom_unique(env):
    appmod, _, inp = env
    with appmod._img_temp(b"a") as p1, appmod._img_temp(b"b") as p2:
        assert p1 != p2
        assert os.path.exists(p1) and os.path.exists(p2)
    assert list(inp.iterdir()) == []


def test_bouton_annuler_present(env):
    _, c, _ = env
    html = c.get("/apprendre").get_data(as_text=True)
    assert 'id="loading-cancel"' in html
    assert html.count("annulerRequete()") >= 3
    assert 'id="inline-load"' in html
    assert "showInline('Gemini analyse ton cours...'" in html
    assert "showLoading('Gemini analyse ton cours...'" not in html


class _Err(Exception):
    def __init__(self, code):
        self.code = code


@pytest.mark.parametrize("code,attendu", [(503, 503), (429, 429), (500, 500)])
def test_erreur_gemini_code(env, monkeypatch, code, attendu):
    appmod, c, _ = env

    def boom(*a, **k):
        raise _Err(code)

    monkeypatch.setattr(appmod, "generer", boom)
    r = c.post("/api/generer", json={"mode": 4, "texte": "x"})
    assert r.status_code == attendu
    assert r.get_json()["error"]


def test_prompts_nettoyes():
    from modules import generator
    assert 2 not in generator.MODES and 1 in generator.MODES
    assert "sans jamais écrire" in generator.SYSTEM_PROMPT
