import json
import pytest

CANDS = [(0, "q", [{"url": f"u{i}", "page": f"File:p{i}.png"} for i in (1, 2, 3)])]


@pytest.mark.parametrize("choix,attendu", [
    ("1.3", [2]), (1.2, [1]), (2, [1]), ("3", [2]),   # formats acceptes
    ("2.1", [0]),                                      # mauvais emplacement : repli
    ("abc", [0]), (9, [0]),                            # illisible / hors limites : repli
    (None, [None]),                                    # rejet explicite
])
def test_choix_vision(monkeypatch, choix, attendu):
    from modules import chat_routes
    monkeypatch.setattr(chat_routes, "_telecharger", lambda u: (b"x", "image/png"))
    rep = json.dumps([{"i": 1, "choix": choix, "raison": "r"}])
    monkeypatch.setattr("modules.gemini_handler.analyser_contenus", lambda c, cfg=None: rep)
    assert chat_routes._vision_choix(CANDS, "contenu") == attendu
