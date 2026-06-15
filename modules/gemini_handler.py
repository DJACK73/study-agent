from google import genai
from google.genai import types
import os, sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import GEMINI_API_KEY, MODEL_NAME

client = genai.Client(api_key=GEMINI_API_KEY)

def analyser_texte(texte: str, prompt: str) -> str:
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=f"{prompt}\n\n---\n{texte}"
    )
    return response.text

def analyser_image(chemin_image: str, prompt: str) -> str:
    with open(chemin_image, "rb") as f:
        image_bytes = f.read()

    ext = os.path.splitext(chemin_image)[1].lower()
    mime_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".pdf": "application/pdf"
    }
    mime = mime_types.get(ext, "image/jpeg")

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime),
            types.Part.from_text(text=prompt)
        ]
    )
    return response.text
