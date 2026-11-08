import os
import types

import httpx

os.environ.setdefault("GEMINI_API_KEY", "dummy")
import pytest  # noqa: E402
from modules import gemini_handler as gh  # noqa: E402


class _Faux:
    def __init__(self, suite):
        self.suite, self.appels, self.models = list(suite), 0, self

    def generate_content(self, model, contents):
        self.appels += 1
        r = self.suite.pop(0)
        if isinstance(r, Exception):
            raise r
        return types.SimpleNamespace(text=r)


@pytest.fixture
def faux(monkeypatch):
    def _make(suite):
        f = _Faux(suite)
        monkeypatch.setattr(gh, "_CLIENTS", [f])
        monkeypatch.setattr(gh.time, "sleep", lambda s: None)
        return f
    return _make


def test_vrai_timeout_httpx_donne_timeouterror_sans_nouvel_essai(faux):
    f = faux([httpx.ReadTimeout("lent")])
    with pytest.raises(TimeoutError):
        gh._appeler("x")
    assert f.appels == 1


def test_connexion_coupee_donne_connectionerror_apres_deux_essais(faux):
    f = faux([httpx.ConnectError("off"), httpx.ConnectError("off")])
    with pytest.raises(ConnectionError):
        gh._appeler("x")
    assert f.appels == 2


def test_connexion_coupee_puis_retablie(faux):
    f = faux([httpx.ConnectError("off"), "ok"])
    assert gh._appeler("x") == "ok"
    assert f.appels == 2


def test_autre_erreur_non_retryee(faux):
    f = faux([ValueError("autre")])
    with pytest.raises(ValueError):
        gh._appeler("x")
    assert f.appels == 1
