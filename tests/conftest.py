from pathlib import Path

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
FORMATS_ROOT = PROJECT_ROOT / "Formatos de PDF"


def find_sample_pdf(file_name: str) -> Path:
    matches = list(FORMATS_ROOT.rglob(file_name))
    if not matches:
        pytest.skip(f"No existe el PDF de prueba: {file_name}")
    return matches[0]


@pytest.fixture(scope="session")
def pdf_path():
    return find_sample_pdf
