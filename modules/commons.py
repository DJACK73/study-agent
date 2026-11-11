"""Images libres de Wikimedia Commons (appel serveur). Aucune URL ne vient de Gemini."""
import html
import os
import re
import threading
import time

import requests

_API = "https://commons.wikimedia.org/w/api.php"
_CONTACT = os.environ.get("COMMONS_CONTACT", "").strip()
_UA = "StudyAgent/1.0 (" + (_CONTACT or "outil d'etude local") + ")"
_TIMEOUT = 10
_LICENCE_OK = re.compile(r"^(cc0|public domain|pd\b|cc[ -]by(?:[ -]sa)?\b)", re.I)
_LICENCE_NON = re.compile(r"\b(nc|nd)\b", re.I)
_TAGS = re.compile(r"<[^>]+>")
_HOTE_IMG = re.compile(r"^https://(?:upload|thumb)\.wikimedia\.org/")
_HOTE_PAGE = re.compile(r"^https://commons\.wikimedia\.org/")
_LANG = re.compile(r" (fr|en)\.\w+$", re.I)

# Un seul point de passage vers l'API : verrou + intervalle minimal + cache.
_VERROU = threading.Lock()
_INTERVALLE = 0.8
_dernier = 0.0
_CACHE = {}
_TTL = 3600
_CACHE_MAX = 64


def _texte(s) -> str:
    return html.unescape(_TAGS.sub("", s or "")).strip()[:120]


def _get(params):
    """GET serialise, espace de _INTERVALLE s, une reprise sur 429 (Retry-After borne a 5 s)."""
    global _dernier
    with _VERROU:
        for essai in range(2):
            attente = _dernier + _INTERVALLE - time.monotonic()
            if attente > 0:
                time.sleep(attente)
            r = requests.get(_API, headers={"User-Agent": _UA}, timeout=_TIMEOUT, params=params)
            _dernier = time.monotonic()
            if getattr(r, "status_code", 200) == 429 and essai == 0:
                try:
                    w = min(float((getattr(r, "headers", {}) or {}).get("Retry-After", 2)), 5.0)
                except (TypeError, ValueError):
                    w = 2.0
                print(f"commons: 429, reprise dans {w:.1f}s")
                time.sleep(w)
                continue
            break
    r.raise_for_status()
    return r


def _recherche(sujet: str) -> list[dict]:
    r = _get({
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": f"filetype:bitmap|drawing {sujet[:80]}", "gsrnamespace": 6, "gsrlimit": 20,
        "prop": "imageinfo", "iiprop": "url|mime|extmetadata", "iiurlwidth": 800,
        "iiextmetadatafilter": "LicenseShortName|Artist|ObjectName"})
    pages = (r.json().get("query") or {}).get("pages") or {}
    out, rejet = [], {"licence": 0, "hote": 0, "mime": 0}
    for p in sorted(pages.values(), key=lambda p: p.get("index", 0)):
        info = (p.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}
        lic = _texte((meta.get("LicenseShortName") or {}).get("value"))
        url, page = info.get("thumburl") or "", info.get("descriptionurl") or ""
        if not lic or not _LICENCE_OK.search(lic) or _LICENCE_NON.search(lic):
            rejet["licence"] += 1
            continue
        if not _HOTE_IMG.match(url) or not _HOTE_PAGE.match(page):
            rejet["hote"] += 1
            continue
        if not str(info.get("mime", "")).startswith("image/"):
            rejet["mime"] += 1
            continue
        nom = str(p.get("title", ""))
        m = _LANG.search(nom)
        titre = _texte((meta.get("ObjectName") or {}).get("value")) or _texte(nom.replace("File:", ""))
        out.append({"url": url, "page": page, "titre": titre,
                    "auteur": _texte((meta.get("Artist") or {}).get("value")) or "Auteur inconnu",
                    "licence": lic, "_k": 0 if (m and m.group(1).lower() == "fr") else 1 if m else 2})
    print(f"commons: {sujet[:40]!r}: {len(pages)} page(s), {len(out)} gardee(s), rejets {rejet}")
    return out


_STOP = {"and", "of", "the", "in", "with", "a", "an"}
_QUEUE = {"diagram", "labeled", "labelled", "scheme", "chart"}


def _variantes(sujet: str) -> list[str]:
    """Requete complete sans mots vides, puis jusqu'a 1 reduction du sujet (la queue 'diagram/labeled' est gardee)."""
    mots = [w for w in sujet.split() if w.lower() not in _STOP]
    queue = []
    while len(mots) > 1 and mots[-1].lower() in _QUEUE:
        queue.insert(0, mots.pop())
    out = [" ".join(mots + queue)]
    for _ in range(2):
        if len(mots) <= 2:
            break
        mots = mots[:-1]
        out.append(" ".join(mots + queue))
    return out


def chercher_images(sujet: str, n: int = 3) -> list[dict]:
    """Jusqu'a n images libres (une requete API, cache 1 h). Fichiers _fr d'abord.
    Leve une exception si la requete echoue."""
    cle = sujet[:80].lower()
    ent = _CACHE.get(cle)
    if ent and time.monotonic() - ent[0] < _TTL:
        items = ent[1]
    else:
        items = []
        for v in ([sujet] if sujet.endswith(" fr") else _variantes(sujet)):
            items = _recherche(v)
            if items:
                break
        if len(_CACHE) >= _CACHE_MAX:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[cle] = (time.monotonic(), items)
    out = sorted(items, key=lambda it: it["_k"])
    return [{k: v for k, v in it.items() if k != "_k"} for it in out[:n]]
