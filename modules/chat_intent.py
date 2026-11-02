import re
import unicodedata


def _n(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower())
                   if unicodedata.category(c) != "Mn")


_PDF = re.compile(r"\bpdf\b")
_TOUT = re.compile(r"toute (la )?(discussion|conversation)|tout le chat|l'ensemble")
_PARTIE = re.compile(
    r"(?:partie|section|chapitre|paragraphe)\s+"
    r"(?:(?:sur|du|de la|de l'|des|de|d')\s*)?([a-z0-9' -]{2,40})")


def detecter_pdf(message: str) -> dict | None:
    """None si pas de demande PDF. Sinon {'portee': 'dernier'|'tout'|'partie', 'partie': str|None}."""
    m = _n(message)
    if not _PDF.search(m):
        return None
    if _TOUT.search(m):
        return {"portee": "tout", "partie": None}
    p = _PARTIE.search(m)
    if p:
        nom = re.sub(r"\s*(en |au format )?pdf.*$", "", p.group(1)).strip(" -'")
        if nom:
            return {"portee": "partie", "partie": nom}
    return {"portee": "dernier", "partie": None}


def extraire_partie(markdown: str, nom: str) -> str | None:
    """Section dont le titre contient `nom`, jusqu'au titre suivant de niveau égal ou supérieur."""
    lignes, debut, niveau = markdown.split("\n"), None, 0
    nom = _n(nom)
    for i, l in enumerate(lignes):
        h = re.match(r"(#+)\s+(.*)", l)
        if not h:
            continue
        if debut is None:
            if nom in _n(h.group(2)):
                debut, niveau = i, len(h.group(1))
        elif len(h.group(1)) <= niveau:
            return "\n".join(lignes[debut:i]).strip()
    return "\n".join(lignes[debut:]).strip() if debut is not None else None
