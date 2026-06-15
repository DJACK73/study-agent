import os

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL_NAME     = "gemini-3.1-flash-lite"
OUTPUT_DIR     = "outputs"
INPUT_DIR      = "inputs"
DB_PATH        = "data/sessions.db"

# Mot de passe d'accès à l'interface
ACCESS_PASSWORD = os.environ.get("ACCESS_PASSWORD", "studyagent2026")
