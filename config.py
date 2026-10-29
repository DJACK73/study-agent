import os


def _list(name: str) -> list[str]:
    return [k.strip() for k in os.environ.get(name, "").split(",") if k.strip()]


GEMINI_API_KEYS = _list("GEMINI_API_KEYS") or _list("GEMINI_API_KEY")
TAVILY_API_KEYS = _list("TAVILY_API_KEYS") or _list("TAVILY_API_KEY")

GEMINI_API_KEY = GEMINI_API_KEYS[0] if GEMINI_API_KEYS else ""  # compat ancien code

MODEL_FAST = os.environ.get("GEMINI_MODEL_FAST", "gemini-3.5-flash-lite")
MODEL_SMART = os.environ.get("GEMINI_MODEL_SMART", "gemini-3.6-flash")
MODEL_NAME = MODEL_FAST  # compat ancien code

OUTPUT_DIR = "outputs"
INPUT_DIR = "inputs"
DB_PATH = "data/sessions.db"

PORT = int(os.environ.get("PORT", "8081"))
