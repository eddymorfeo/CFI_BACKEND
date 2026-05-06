from decimal import Decimal

from app.parsers.banco_estado.chequera_electronica_parser import (
    BancoEstadoChequeraElectronicaParser,
)


def test_chequera_electronica_detecta_y_extrae_movimientos(pdf_path):
    parser = BancoEstadoChequeraElectronicaParser()
    path = pdf_path("CARTOL_1.PDF")

    result = parser.parse(str(path))
    metadata = result["document_metadata"]

    assert parser.can_parse(str(path)) is True
    assert result["parser_code"] == "BANCO_ESTADO_CHEQUERA_ELECTRONICA"
    assert len(result["movements"]) == 36
    assert metadata["detected_holder_name"] == "JARAMILLO AGUDELO NATALIA"
    assert metadata["detected_account_number"] == "355-7-125605-1"
    assert metadata["document_date_from"].isoformat() == "2022-07-28"
    assert metadata["document_date_to"].isoformat() == "2022-08-29"


def test_chequera_electronica_infiere_cargo_y_abono_por_saldo(pdf_path):
    parser = BancoEstadoChequeraElectronicaParser()
    result = parser.parse(str(pdf_path("CARTOL_1.PDF")))

    first_movement = result["movements"][0]
    third_movement = result["movements"][2]

    assert first_movement["description"] == "BCO SANTANDER CHILE"
    assert first_movement["charge_amount"] == Decimal("0")
    assert first_movement["deposit_amount"] == Decimal("50000")
    assert first_movement["balance_amount"] == Decimal("51578")

    assert third_movement["description"] == "COMPRA COPEC CAMINO CL"
    assert third_movement["charge_amount"] == Decimal("5004")
    assert third_movement["deposit_amount"] == Decimal("0")
    assert third_movement["balance_amount"] == Decimal("51574")


def test_chequera_electronica_multiples_cartolas_resuelve_fechas_por_pagina(pdf_path):
    parser = BancoEstadoChequeraElectronicaParser()
    path = pdf_path("1.pdf")

    result = parser.parse(str(path))
    metadata = result["document_metadata"]

    assert parser.can_parse(str(path)) is True
    assert result["parser_code"] == "BANCO_ESTADO_CHEQUERA_ELECTRONICA"
    assert len(result["movements"]) == 2543
    assert metadata["detected_holder_name"] == "VERGARA ROJAS NATHALY ALEJANDRA"
    assert metadata["detected_account_number"] == "356-7-036969-1"
    assert metadata["document_date_from"].isoformat() == "2022-07-18"
    assert metadata["document_date_to"].isoformat() == "2025-06-05"

    leap_day_movement = result["movements"][1455]
    assert leap_day_movement["transaction_date"].isoformat() == "2024-02-29"
    assert leap_day_movement["description"] == "TEF DE GAJARDO CANETE CAMILO IGNACI"
    assert leap_day_movement["deposit_amount"] == Decimal("10000")

    atm_movement = result["movements"][8]
    assert atm_movement["document_number"] is None
    assert atm_movement["description"] == "CAJ.AUT GIRO CAJERO AUTOMATICO 21/07 17:10"
    assert atm_movement["charge_amount"] == Decimal("50000")
    assert atm_movement["detected_movement_type"] == "WITHDRAWAL"
