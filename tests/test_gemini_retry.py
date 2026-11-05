import pytest
import modules.gemini_handler as gh


class Err(Exception):
    def __init__(self, code):
        self.code = code


class Fake:
    def __init__(self, seq, appels):
        self.seq, self.appels = seq, appels
        self.models = self

    def generate_content(self, model, contents):
        self.appels.append(model)
        r = self.seq.pop(0)
        if isinstance(r, Exception):
            raise r

        class R:
            text = r
        return R()


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setattr(gh.time, "sleep", lambda s: None)
    appels = []

    def mk(*seqs):
        monkeypatch.setattr(gh, "_CLIENTS", [Fake(list(s), appels) for s in seqs])
    return mk, appels


def test_503_puis_cle2_ok(setup):
    mk, appels = setup
    mk([Err(503)], ["OK"])
    assert gh._appeler("x") == "OK"
    assert appels == [gh.MODEL_NAME, gh.MODEL_NAME]


def test_dernier_essai_modele_smart(setup):
    mk, appels = setup
    mk([Err(503), Err(503)], [Err(429), "OK"])
    assert gh._appeler("x") == "OK"
    assert appels[-1] == gh.MODEL_SMART


def test_erreur_non_transitoire_immediate(setup):
    mk, appels = setup
    mk([Err(403)], ["OK"])
    with pytest.raises(Err):
        gh._appeler("x")
    assert len(appels) == 1


def test_echec_total(setup):
    mk, appels = setup
    mk([Err(503), Err(503)], [Err(503), Err(503)])
    with pytest.raises(Err):
        gh._appeler("x")
    assert len(appels) == 4
