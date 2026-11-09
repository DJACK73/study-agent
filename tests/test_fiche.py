import io
import pytest
from pypdf import PdfReader
from modules.exporters.pdf import generer_pdf_bytes


def test_fiche_courte_une_page():
    b = generer_pdf_bytes("# Titre\n\n## Bloc\n- α ≥ 2\n- é à ç", "Fiche", "fiche")
    assert len(PdfReader(io.BytesIO(b)).pages) == 1


def test_fiche_trop_longue_refusee():
    texte = "# T\n" + "\n".join(f"- ligne numero {i} avec un peu de texte" for i in range(300))
    with pytest.raises(ValueError):
        generer_pdf_bytes(texte, "Fiche", "fiche")
