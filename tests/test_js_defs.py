import re
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
HANDLER = re.compile(r'\bon(?:click|change|input|keyup|submit)\s*=\s*"\s*([A-Za-z_$][\w$]*)\s*\(')
SKIP = {"if", "return", "event", "confirm", "alert", "this"}


def test_handlers_inline_definis():
    htmls = list(ROOT.glob("templates/*.html"))
    src = "\n".join(p.read_text(encoding="utf-8") for p in [*htmls, *ROOT.glob("static/*.js")])
    noms = set()
    for p in htmls:
        noms |= set(HANDLER.findall(p.read_text(encoding="utf-8")))
    manquants = []
    for n in sorted(noms - SKIP):
        e = re.escape(n)
        if not re.search(r"function\s+" + e + r"\b|(?:const|let|var)\s+" + e + r"\s*=|window\." + e + r"\s*=", src):
            manquants.append(n)
    assert not manquants, "handlers sans definition: %s" % manquants
