"""Images libres de Wikimedia Commons (appel serveur). Aucune URL ne vient de Gemini."""
import html
import re

import requests

_API = "https://commons.wikimedia.org/w/api.php"
_UA = "StudyAgent/1.0 (outil d'etude local)"
_TIMEOUT = 10
_LICENCE_OK = re.compile(r"^(cc0|public domain|pd\b|cc[ -]by(?:[ -]sa)?\b)", re.I)
_LICENCE_NON = re.compile(r"\b(nc|nd)\b", re.I)
_TAGS = re.compile(r"<[^>]+>")
_HOTE_IMG = re.compile(r"^https://(?:upload|thumb)\.wikimedia\.org/")
_HOTE_PAGE = re.compile(r"^https://commons\.wikimedia\.org/")


def _texte(s) -> str:
    return html.unescape(_TAGS.sub("", s or "")).strip()[:120]


_LANG = re.compile(r" (fr|en)\.\w+$", re.I)
_SCHEMA = re.compile(r"diagram|labell?ed|scheme|chart", re.I)


def _recherche(sujet: str, ft: str) -> list[dict]:
    r = requests.get(_API, headers={"User-Agent": _UA}, timeout=_TIMEOUT, params={
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": f"{sujet[:80]} filetype:{ft}", "gsrnamespace": 6, "gsrlimit": 12,
        "prop": "imageinfo", "iiprop": "url|mime|extmetadata", "iiurlwidth": 800,
        "iiextmetadatafilter": "LicenseShortName|Artist|ObjectName"})
    r.raise_for_status()
    pages = (r.json().get("query") or {}).get("pages") or {}
    out = []
    for p in sorted(pages.values(), key=lambda p: p.get("index", 0)):
        info = (p.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}
        lic = _texte((meta.get("LicenseShortName") or {}).get("value"))
        url, page = info.get("thumburl") or "", info.get("descriptionurl") or ""
        if not lic or not _LICENCE_OK.search(lic) or _LICENCE_NON.search(lic):
            continue
        if not _HOTE_IMG.match(url) or not _HOTE_PAGE.match(page):
            continue
        if not str(info.get("mime", "")).startswith("image/"):
            continue
        nom = str(p.get("title", ""))
        m = _LANG.search(nom)
        titre = _texte((meta.get("ObjectName") or {}).get("value")) or _texte(nom.replace("File:", ""))
        out.append({"url": url, "page": page, "titre": titre,
                    "auteur": _texte((meta.get("Artist") or {}).get("value")) or "Auteur inconnu",
                    "licence": lic, "_k": 0 if (m and m.group(1).lower() == "fr") else 1 if m else 2})
    return out


def chercher_images(sujet: str, n: int = 3) -> list[dict]:
    """Jusqu'a n images libres. Schemas (SVG) d'abord si la requete parle de diagramme.
    Leve une exception seulement si toutes les recherches echouent."""
    ordre = ("drawing", "bitmap") if _SCHEMA.search(sujet) else ("bitmap", "drawing")
    out, vus, derniere, echecs = [], set(), None, 0
    for ft in ordre:
        try:
            items = _recherche(sujet, ft)
        except Exception as e:
            derniere, echecs = e, echecs + 1
            continue
        deja = set(vus)
        for it in items:
            vus.add(it["page"])
            if it["page"] not in deja:
                out.append(it)
        if len(out) >= n:
            break
    if not out and echecs == len(ordre):
        raise derniere
    out.sort(key=lambda it: it["_k"])
    return [{k: v for k, v in it.items() if k != "_k"} for it in out[:n]]
