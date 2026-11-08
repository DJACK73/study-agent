import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASE = (ROOT / "templates" / "base.html").read_text(encoding="utf-8")
FICHIERS = sorted((ROOT / "templates").glob("*.html")) + [ROOT / "static" / "apprendre.js", ROOT / "static" / "chat.js"]
BRUTES = re.compile(r"rgba\((108,99,255|61,220,132|255,209,102|255,107,107|13,15,20|255,255,255),")


def test_trois_themes_et_bouton():
    assert ':root[data-theme="light"]' in BASE
    assert "prefers-color-scheme: light" in BASE and ":root:not([data-theme])" in BASE
    assert 'id="theme-toggle"' in BASE and "localStorage" in BASE


def test_aucune_couleur_translucide_en_dur():
    for f in FICHIERS:
        assert not BRUTES.search(f.read_text(encoding="utf-8")), f.name


def _lin(c):
    c /= 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _lum(h):
    r, g, b = (int(h[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def _ratio(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_contrastes_theme_clair():
    bloc = re.search(r':root\[data-theme="light"\]\s*\{([^}]*)\}', BASE).group(1)
    v = dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9A-Fa-f]{6})", bloc))
    for nom in ("text", "text2", "text3", "accent2", "green", "yellow", "red"):
        for fond in ("bg", "bg2"):
            r = _ratio(v[nom], v[fond])
            assert r >= 4.5, f"{nom} sur {fond} : {r:.2f}"
