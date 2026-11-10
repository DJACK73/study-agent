from google import genai
from google.genai import types
import importlib, os, sys, time, logging
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import GEMINI_API_KEY, MODEL_NAME, MODEL_SMART

_KEYS = [k for k in (GEMINI_API_KEY, os.environ.get("GEMINI_API_KEY_2")) if k] or [GEMINI_API_KEY]
_TIMEOUT_MS = 120_000
_CLIENTS = [genai.Client(api_key=k, http_options=genai.types.HttpOptions(timeout=_TIMEOUT_MS)) for k in _KEYS]
_DELAIS = (2, 5, 5)  # attente avant les essais 2, 3 et 4
_RETRY = (429, 503)


def _classes(nom):
    # classes httpx (et httpx2 si installe) levees telles quelles par le SDK
    out = []
    for m in ("httpx", "httpx2"):
        try:
            out.append(getattr(importlib.import_module(m), nom))
        except Exception:
            pass
    return tuple(out)


_TIMEOUTS = _classes("TimeoutException")
_CONNEXIONS = _classes("ConnectError")

if "pytest" not in sys.modules:  # journal fichier hors tests : data/gemini.log (hors git)
    from logging.handlers import RotatingFileHandler
    _data = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    os.makedirs(_data, exist_ok=True)
    _fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    _racine = logging.getLogger()
    _hf = RotatingFileHandler(os.path.join(_data, "gemini.log"), maxBytes=200_000, backupCount=3, encoding="utf-8")
    _hf.setLevel(logging.WARNING)
    _hf.setFormatter(_fmt)
    _racine.addHandler(_hf)
    if len(_racine.handlers) == 1:  # aucun autre handler : garder les alertes dans le terminal
        _hs = logging.StreamHandler()
        _hs.setLevel(logging.WARNING)
        _hs.setFormatter(_fmt)
        _racine.addHandler(_hs)


import contextvars as _cv

MODELE_BASE = _cv.ContextVar("modele_base", default=None)


def _appeler(contents) -> str:
    """Retry sur 429/503, alterne les clés, dernier essai sur MODEL_SMART."""
    n = len(_DELAIS) + 1
    derniere = None
    for i in range(n):
        if i:
            time.sleep(_DELAIS[i - 1])
        client = _CLIENTS[i % len(_CLIENTS)]
        modele = (MODELE_BASE.get() or MODEL_NAME) if i < n - 1 else MODEL_SMART
        try:
            return client.models.generate_content(model=modele, contents=contents).text
        except Exception as e:
            if isinstance(e, _TIMEOUTS) or "Timeout" in type(e).__name__:
                raise TimeoutError("Gemini ne repond pas (delai depasse)") from e
            if isinstance(e, _CONNEXIONS):
                logging.warning("gemini connexion impossible %d/%d modele=%s cle=%d",
                                i + 1, n, modele, i % len(_CLIENTS) + 1)
                if i >= 1:
                    raise ConnectionError("Gemini injoignable (connexion impossible)") from e
                derniere = e
                continue
            if getattr(e, "code", None) not in _RETRY:
                raise
            derniere = e
            logging.warning("gemini retry %d/%d code=%s modele=%s cle=%d",
                            i + 1, n, getattr(e, "code", None), modele, i % len(_CLIENTS) + 1)
    raise derniere


def analyser_texte(texte: str, prompt: str) -> str:
    return _appeler(f"{prompt}\n\n---\n{texte}")


def analyser_image(chemin_image: str, prompt: str) -> str:
    with open(chemin_image, "rb") as f:
        image_bytes = f.read()

    ext = os.path.splitext(chemin_image)[1].lower()
    mime_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".pdf": "application/pdf",
    }
    mime = mime_types.get(ext, "image/jpeg")

    return _appeler([
        types.Part.from_bytes(data=image_bytes, mime_type=mime),
        types.Part.from_text(text=prompt),
    ])
