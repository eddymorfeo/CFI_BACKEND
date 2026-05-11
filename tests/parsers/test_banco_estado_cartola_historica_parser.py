from decimal import Decimal
from pathlib import Path

import pytest

from app.parsers.banco_estado.cartola_historica_parser import BancoEstadoCartolaHistoricaParser


def test_cartola_historica_banco_estado_soporta_documentos_cortos():
    path = Path.home() / "Downloads" / "2022.pdf"
    if not path.exists():
        pytest.skip(f"No existe el PDF de prueba: {path}")

    parser = BancoEstadoCartolaHistoricaParser()
    result = parser.parse(str(path))

    assert parser.can_parse(str(path)) is True
    assert len(result["movements"]) == 108

    first_movement = result["movements"][0]
    assert first_movement["document_number"] == "1562"
    assert first_movement["description"] == "DEPOSITO EN EFECTIVO CAJA VECINA"
    assert first_movement["deposit_amount"] == Decimal("5000")
    assert first_movement["balance_amount"] == Decimal("8183")

    commission = result["movements"][1]
    assert commission["document_number"] == "1212"
    assert commission["description"] == "COMISION TRANSACCION INTERNACIONAL"
    assert commission["charge_amount"] == Decimal("482")

    transfer = result["movements"][30]
    assert transfer["document_number"] == "1077"
    assert transfer["description"] == "TEF DE REYES GOMEZ PAOLA ANDREA"
    assert transfer["deposit_amount"] == Decimal("15000")


def test_cartola_historica_banco_estado_soporta_documento_alfanumerico():
    parser = BancoEstadoCartolaHistoricaParser()

    logical_row = {
        "prefix_rows": [],
        "anchor_row": [
            {"text": "AB-12", "x0": 55, "top": 100},
            {"text": "COMPRA", "x0": 121, "top": 100},
            {"text": "PRUEBA", "x0": 160, "top": 100},
            {"text": "$", "x0": 327, "top": 100},
            {"text": "1.234", "x0": 335, "top": 100},
            {"text": "$", "x0": 427, "top": 100},
            {"text": "0", "x0": 435, "top": 100},
            {"text": "05/11/2022", "x0": 452, "top": 100},
            {"text": "$", "x0": 559, "top": 100},
            {"text": "9.876", "x0": 567, "top": 100},
        ],
        "suffix_rows": [],
    }

    movement = parser._parse_logical_row(
        logical_row=logical_row,
        row_number=1,
        page_number=1,
    )

    assert movement is not None
    assert movement["document_number"] == "AB-12"
    assert movement["description"] == "COMPRA PRUEBA"
    assert movement["charge_amount"] == Decimal("1234")
    assert movement["deposit_amount"] == Decimal("0")
    assert movement["balance_amount"] == Decimal("9876")
