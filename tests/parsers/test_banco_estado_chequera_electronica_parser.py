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
