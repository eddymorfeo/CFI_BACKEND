from decimal import Decimal

from app.parsers.banco_chile.cuenta_vista_estado_cuenta_parser import (
    BancoChileCuentaVistaEstadoCuentaParser,
)


def test_cv_sandra_extrae_fila_de_pagina_de_continuacion(pdf_path):
    parser = BancoChileCuentaVistaEstadoCuentaParser()
    result = parser.parse(str(pdf_path("CV Sandra Sanhueza.pdf")))

    assert result["parser_code"] == "BANCO_CHILE_CUENTA_VISTA_ESTADO_CUENTA"
    assert len(result["movements"]) == 550

    continuation_rows = [
        movement
        for movement in result["movements"]
        if movement["transaction_date"].isoformat() == "2026-02-02"
        and movement["description"] == "TRASPASO DE CUENTA:000265424239"
        and movement["deposit_amount"] == Decimal("40000")
    ]

    assert len(continuation_rows) == 1
    assert continuation_rows[0]["page_number"] == 2
    assert continuation_rows[0]["charge_amount"] == Decimal("0")
    assert continuation_rows[0]["balance_amount"] == Decimal("40508")


def test_traspaso_de_cuenta_sin_separador_es_abono(pdf_path):
    parser = BancoChileCuentaVistaEstadoCuentaParser()
    result = parser.parse(str(pdf_path("CV Sandra Sanhueza.pdf")))

    transfer_rows = [
        movement
        for movement in result["movements"]
        if "TRASPASO DE CUENTA000265424239" in movement["description"]
    ]

    assert transfer_rows
    assert all(movement["charge_amount"] == Decimal("0") for movement in transfer_rows)
    assert all(movement["deposit_amount"] > Decimal("0") for movement in transfer_rows)
    assert all(movement["detected_movement_type"] == "TRANSFER_IN" for movement in transfer_rows)
