import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_cartes_en_anki_echappe_et_ignore_les_vides():
    node = shutil.which("node")
    if not node:
        pytest.skip("node absent")
    js = (ROOT / "static/apprendre.js").read_text(encoding="utf-8")
    m = re.search(r"function cartesEnAnki\(.*?\n}\n", js, re.S)
    assert m, "cartesEnAnki introuvable"
    prog = m.group(0) + r'''
process.stdout.write(JSON.stringify(cartesEnAnki([
  {question: 'Q "a"', reponse: 'R1\nR2'},
  {question: '', reponse: 'x'},
  {question: 'P', answer: 'é\tz'}
])));
'''
    out = subprocess.run([node, "-"], input=prog, capture_output=True, text=True, check=True, timeout=20).stdout
    assert json.loads(out) == '"Q ""a"""\t"R1\nR2"\nP\t"é\tz"\n'
