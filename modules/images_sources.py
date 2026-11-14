"""Sources d'images complementaires (Serper, Pixabay). Appelees seulement s'il manque des candidats Commons."""
import json
import os
import re
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

import config
from core.keypool import KeyPool

_USAGE = Path(__file__).resolve().parent.parent / "data" / "serper_usage.json"
_SERPER_MAX = int(os.environ.get("SERPER_MAX", "2400"))  # par cle
_ACTIF = os.environ.get("IMAGES_WEB", "1") != "0"
_TTLS = {"pixabay": 86400, "serper": 3600}
_CACHE_MAX, _TIMEOUT = 64, 15
_QUOTA = {402, 403, 429}
_CACHE: dict = {}
_pools: dict = {}
_verrou = threading.Lock()
_EXCLUS = ("pinterest.", "instagram.", "facebook.", "tiktok.", "alamy.", "shutterstock.", "gettyimages.",
           "istockphoto.", "dreamstime.", "123rf.", "depositphotos.", "wikimedia.org", "wikipedia.org")
_RE_IA = re.compile(r"\b(ai|ia|midjourney|dall-?e)\b|stable diffusion|g[ée]n[ée]r[ée]e?s?\b|generated", re.I)


def _en_cache(src, q):
    ent = _CACHE.get((src, q.lower()[:80]))
    if ent and time.monotonic() - ent[0] < _TTLS.get(src, 3600):
        return ent[1]
    return None


def _mettre(src, q, items):
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[(src, q.lower()[:80])] = (time.monotonic(), items)


def _appeler(nom, cles, appel, pause):
    """JSON de la reponse, ou None. Rotation sur quota (402/403/429) : la cle est mise en pause."""
    pool = _pools.setdefault(nom, KeyPool(cles))
    for _ in range(len(cles)):
        cle = pool.get()
        if cle is None:
            break
        try:
            r = appel(cle)
        except requests.RequestException as e:
            print(f"images {nom}: {type(e).__name__}")
            return None
        if r.status_code == 200:
            return r.json()
        print(f"images {nom}: HTTP {r.status_code}")
        if r.status_code in _QUOTA:
            pool.penalize(cle, pause)
            continue
        return None
    return None


def _utilises():
    try:
        return int(json.loads(_USAGE.read_text(encoding="utf-8")).get("n", 0))
    except (OSError, ValueError, AttributeError):
        return 0


def _plafond():
    return _SERPER_MAX * max(1, len(config.SERPER_API_KEYS))


def _compter():
    with _verrou:
        n = _utilises() + 1
        try:
            _USAGE.parent.mkdir(parents=True, exist_ok=True)
            _USAGE.write_text(json.dumps({"n": n}), encoding="utf-8")
        except OSError as e:
            print(f"images serper: compteur: {e}")
    if n == int(_plafond() * 0.8):
        print(f"images serper: 80 % du plafond atteint ({n}/{_plafond()})")


def serper(q, n=6):
    cles = config.SERPER_API_KEYS
    if not cles or _utilises() >= _plafond():
        return []
    items = _en_cache("serper", q)
    if items is None:
        j = _appeler("serper", cles, lambda k: requests.post(
            "https://google.serper.dev/images", headers={"X-API-KEY": k, "Content-Type": "application/json"},
            json={"q": q[:150], "num": 10}, timeout=_TIMEOUT), 3600)
        if j is None:
            return []
        _compter()
        items = []
        for x in j.get("images", []):
            url, page = x.get("imageUrl") or "", x.get("link") or ""
            host = urlparse(page).netloc.lower()
            if not url.startswith(("http://", "https://")) or not page.startswith("http") or any(d in host for d in _EXCLUS):
                continue
            items.append({"url": url, "vignette": x.get("thumbnailUrl") or "", "page": page,
                          "titre": (x.get("title") or host)[:120], "auteur": host,
                          "licence": "Licence non vérifiée", "source": "serper"})
        print(f"images serper: {q[:40]!r}: {len(items)} gardee(s), {_utilises()}/{_plafond()} credits")
        _mettre("serper", q, items)
    return items[:n]


def pixabay(q, n=6):
    cles = config.PIXABAY_API_KEYS
    if not cles:
        return []
    items = _en_cache("pixabay", q)
    if items is None:
        items, vus, ok = [], set(), False
        for typ in ("illustration", "vector"):
            j = _appeler("pixabay", cles, lambda k, t=typ: requests.get(
                "https://pixabay.com/api/", params={"key": k, "q": q[:100], "lang": "en", "image_type": t,
                                                    "per_page": 8, "safesearch": "true"}, timeout=_TIMEOUT), 60)
            if j is None:
                continue
            ok = True
            for h in j.get("hits", []):
                tags = str(h.get("tags") or "")
                url, page = h.get("webformatURL") or "", h.get("pageURL") or ""
                if not url or not page or page in vus or _RE_IA.search(tags):
                    continue
                vus.add(page)
                items.append({"url": url, "page": page,
                              "titre": ", ".join(t.strip() for t in tags.split(",")[:3]),
                              "auteur": str(h.get("user") or "Pixabay"),
                              "licence": "Licence Pixabay", "source": "pixabay"})
        print(f"images pixabay: {q[:40]!r}: {len(items)} gardee(s)")
        if ok:
            _mettre("pixabay", q, items)
    return items[:n]


def complements(q, deja, k):
    """Jusqu'a k candidats : Serper d'abord (schemas legendes), Pixabay complete. [] si desactive ou sans cle."""
    if not _ACTIF or k <= 0:
        return []
    out, vus = [], set(deja)
    for src in (serper, pixabay):
        if len(out) >= k:
            break
        try:
            lot = src(q)
        except Exception as e:
            print(f"images {getattr(src, '__name__', 'source')}: {e}")
            continue
        for x in lot:
            if len(out) >= k:
                break
            if x["page"] not in vus:
                vus.add(x["page"])
                out.append(x)
    return out


def vider_caches():
    """Vide les caches en memoire (sources d'images + Commons). Ne touche a aucun fichier. Retourne le nombre d'entrees."""
    n = len(_CACHE)
    _CACHE.clear()
    try:
        from modules import commons
        n += len(commons._CACHE)
        commons._CACHE.clear()
    except Exception as e:
        print(f"images cache: {e}")
    return n
