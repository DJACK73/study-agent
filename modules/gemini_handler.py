from google import genai
from google.genai import types
import os, sys, time
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import GEMINI_API_KEY, MODEL_NAME, MODEL_SMART

_KEYS = [k for k in (GEMINI_API_KEY, os.environ.get("GEMINI_API_KEY_2")) if k] or [GEMINI_API_KEY]
_CLIENTS = [genai.Client(api_key=k) for k in _KEYS]
_DELAIS = (2, 5, 5)  # attente avant les essais 2, 3 et 4
_RETRY = (429, 503)


def _appeler(contents) -> str:
    """Retry sur 429/503, alterne les clés, dernier essai sur MODEL_SMART."""
    n = len(_DELAIS) + 1
    derniere = None
    for i in range(n):
        if i:
            time.sleep(_DELAIS[i - 1])
        client = _CLIENTS[i % len(_CLIENTS)]
        modele = MODEL_NAME if i < n - 1 else MODEL_SMART
        try:
            return client.models.generate_content(model=modele, contents=contents).text
        except Exception as e:
            if getattr(e, "code", None) not in _RETRY:
                raise
            derniere = e
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
