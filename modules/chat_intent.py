import json
import os
import re
import time
import unicodedata

_LOG = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "intent_log.jsonl")


def _n(s: str) -> str:
    s = s.replace("’", "'").lower()
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


_PDF = re.compile(r"\bpdf\b|\bimprimable\b|\ba imprimer\b")
_PROCHE = re.compile(r"imprim|telecharg|export|document|fichier")
_TOUT = re.compile(r"\btoute (?:la )?(?:discussion|conversation)\b|\btout le chat\b|\bl'ensemble\b")
_ART = r"(?:(?:sur|du|de|des|la|le|les)\s+|d'|l')*"
_PARTIE = re.compile(r"\b(?:partie|section|chapitre|paragraphe)\s+" + _ART + r"([a-z0-9][a-z0-9' -]{1,39})")
_SUJET_A = re.compile(r"\b(?:expose|lecon|cours|resume|fiche|synthese)\s+(?:complet\s+)?(?:sur|de|du|des|d')\s*(.{3,80})")
_SUJET_B = re.compile(r"\bpdf\s+(?:sur|de|du|des|d')\s*(.{3,80})")
_FIN = re.compile(r"\s+(?:en pdf|au format|pdf|svp|stp|s'il|merci)\b|[,;.!?]")
_GENERIQUE = {"lecon", "cours", "expose", "reponse", "message", "resume", "fiche",
              "discussion", "conversation", "chat", "ca", "cela", "tout"}


def _nettoyer(txt: str) -> str:
    return _FIN.split(txt)[0].strip(" -'")


def detecter_pdf(message: str) -> dict | None:
    """None si pas de demande PDF.
    Sinon {'portee': 'dernier'|'tout'|'partie', 'partie': str|None, 'sujet': str|None}."""
    m = _n(message)
    if not _PDF.search(m):
        return None
    r = {"portee": "dernier", "partie": None, "sujet": None}
    if _TOUT.search(m):
        r["portee"] = "tout"
        return r
    p = _PARTIE.search(m)
    if p:
        nom = _nettoyer(p.group(1))
        if nom:
            r.update(portee="partie", partie=nom)
            return r
    for rx in (_SUJET_A, _SUJET_B):
        s = rx.search(m)
        if s:
            sujet = _nettoyer(s.group(1))
            mots = re.sub(r"^(?:la|le|les|l'|un|une)\s*", "", sujet).split()
            if mots and mots[0] not in _GENERIQUE:
                r["sujet"] = sujet
                break
    return r


def sujet_dans(texte: str, sujet: str) -> bool:
    """True si le sujet demandé apparaît déjà dans le texte (évite de régénérer)."""
    mots = [w for w in re.findall(r"[a-z0-9]{4,}", _n(sujet))]
    t = _n(texte)
    return bool(mots) and all(w in t for w in mots)


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


def journaliser_rate(message: str, resultat: dict | None) -> None:
    """Note les messages proches d'une demande PDF non reconnus (amélioration continue)."""
    if resultat is None and _PROCHE.search(_n(message)):
        os.makedirs(os.path.dirname(_LOG), exist_ok=True)
        with open(_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": time.strftime("%Y-%m-%d %H:%M"), "m": message[:200]},
                               ensure_ascii=False) + "\n")


_DEMANDE_IMG = re.compile(r"\b(?:montre|montrer|affiche|afficher|cherche|chercher|trouve|trouver|donne|donner|veux|voir|vois|illustre|illustrer|ajoute|ajouter)\b")
_IMG = re.compile(r"\b(?:images?|photos?|illustrations?)\s+(?:(?:des|de|du|sur)\s+|d')(.{3,80})")
_ARTICLE = re.compile(r"^(?:(?:la|le|les|un|une|ma|mon|des|du|de)\s+|l'|l\u2019)", re.I)
_GEN_IMG = _GENERIQUE | {"ce", "cette", "cet", "ces", "pdf"}


def detecter_image(message: str) -> str | None:
    """Sujet d'une demande d'image (« montre-moi une image de X »), sinon None."""
    m = _n(message)
    if not _DEMANDE_IMG.search(m):
        return None
    s = _IMG.search(m)
    if not s:
        return None
    debut, fin = s.start(1), s.end(1)
    coupe = _FIN.search(m, debut, fin)
    if coupe:
        fin = coupe.start()
    base = message if len(m) == len(message) else m
    sujet = _ARTICLE.sub("", base[debut:fin].strip(" -'\u2019")).strip()
    mots = _n(sujet).split()
    if len(sujet) < 3 or not mots or mots[0] in _GEN_IMG:
        return None
    return sujet[:80]


_VEUT_IMG = re.compile(r"\b(?:montre|montres|montrer|montrez|affiche|affiches|afficher|ajoute|ajoutes|ajouter|avec|en)\s+(?:moi\s+)?(?:(?:des|de|quelques|une|un|les|la|ses|leurs)\s+)*(?:images?|photos?|illustrations?|schemas?)\b")


def veut_images(message: str) -> bool:
    """True si l'etudiant veut des images EN PLUS de la reponse (« ... et montre des images »)."""
    return bool(_VEUT_IMG.search(_n(message)))
