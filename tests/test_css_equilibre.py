import os
os.environ.setdefault("GEMINI_API_KEY", "dummy")
import re
import pytest


@pytest.mark.parametrize("url", ["/discuter", "/apprendre"])
def test_css_accolades_equilibrees(monkeypatch, url):
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    import app as appmod
    r = appmod.app.test_client().get(url)
    assert r.status_code == 200
    blocs = re.findall(r"<style[^>]*>(.*?)</style>", r.get_data(as_text=True), re.S)
    assert blocs
    for css in blocs:
        assert css.count("{") == css.count("}")
