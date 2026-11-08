import ast
import os
from pathlib import Path

os.environ.setdefault("GEMINI_API_KEY", "dummy")
from modules import generator  # noqa: E402


def _chat_prompt() -> str:
    src = (Path(__file__).resolve().parent.parent / "modules" / "chat_routes.py").read_text(encoding="utf-8")
    for n in ast.parse(src).body:
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "CHAT_PROMPT":
            return ast.literal_eval(n.value)
    raise AssertionError("CHAT_PROMPT introuvable")


def test_systeme_contraintes_dures():
    s = generator.SYSTEM_PROMPT
    assert "français" in s and "préambule" in s and "accents" in s


def test_modes_heritent_du_systeme():
    for m in (1, 3, 4, 9):
        assert generator.SYSTEM_PROMPT in generator.MODES[m]


def test_formats_json_flashcards_et_qcm():
    f, q = generator.MODES[3], generator.MODES[4]
    assert "JSON" in f and '"question"' in f and '"reponse"' in f
    assert "JSON" in q and all(k in q for k in ('"question"', '"choix"', '"reponse"', '"explication"'))


def test_examen_marqueur_et_questions_sans_reponses():
    e = generator.MODES[9]
    assert "--- CORRIGÉ ---" in e and "SANS les réponses" in e


def test_chat_prompt_contraintes():
    p = _chat_prompt()
    assert "français" in p and "je ne sais pas" in p and "URL" in p
