from decimal import Decimal

from app.parsers.banco_estado.cuenta_corriente_parser import BancoEstadoCuentaCorrienteParser
from app.parsers.parser_registry import get_available_parsers


def test_cuenta_corriente_banco_estado_detecta_y_extrae_movimientos(pdf_path):
    parser = BancoEstadoCuentaCorrienteParser()
    path = pdf_path("CARTOLA CTA CTE.pdf")

    result = parser.parse(str(path))
    metadata = result["document_metadata"]

    assert parser.can_parse(str(path)) is True
    assert result["parser_code"] == "BANCO_ESTADO_CUENTA_CORRIENTE_CARTOLA_HISTORICA"
    assert len(result["movements"]) == 527
    assert metadata["detected_institution_name"] == "BancoEstado"
    assert metadata["detected_holder_name"] == "NATHALY ALEJANDRA VERGARA ROJAS"
    assert metadata["detected_account_number"] == "356-0-002170-1"
    assert metadata["detected_account_type"] == "CUENTA CORRIENTE"
    assert metadata["document_date_from"].isoformat() == "2023-08-18"
    assert metadata["document_date_to"].isoformat() == "2025-05-15"


def test_cuenta_corriente_banco_estado_infiere_cargos_abonos_y_anos(pdf_path):
    parser = BancoEstadoCuentaCorrienteParser()
    result = parser.parse(str(pdf_path("CARTOLA CTA CTE.pdf")))

    first_movement = result["movements"][0]
    second_movement = result["movements"][1]
    cross_year_movement = result["movements"][35]
    negative_balance_movement = result["movements"][383]

    assert first_movement["transaction_date"].isoformat() == "2023-10-20"
    assert first_movement["description"] == "TEF BANCOESTADO DE BRICENO PALMA EU"
    assert first_movement["charge_amount"] == Decimal("0")
    assert first_movement["deposit_amount"] == Decimal("100000")
    assert first_movement["balance_amount"] == Decimal("100000")
    assert first_movement["detected_movement_type"] == "TRANSFER_IN"

    assert second_movement["description"] == "TEF A VERGARA ROJAS NATHALY ALEJAND"
    assert second_movement["charge_amount"] == Decimal("100000")
    assert second_movement["deposit_amount"] == Decimal("0")
    assert second_movement["balance_amount"] == Decimal("0")
    assert second_movement["detected_movement_type"] == "TRANSFER_OUT"

    assert cross_year_movement["transaction_date"].isoformat() == "2024-01-05"
    assert cross_year_movement["description"] == "TEF BANCOESTADO DE MORIS ZAMORANO C"
    assert cross_year_movement["deposit_amount"] == Decimal("5000")
    assert cross_year_movement["balance_amount"] == Decimal("5000")

    assert negative_balance_movement["transaction_date"].isoformat() == "2024-10-02"
    assert negative_balance_movement["description"] == "TEF A VELASQUEZ BRICENO CRISTOBAL I"
    assert negative_balance_movement["charge_amount"] == Decimal("100000")
    assert negative_balance_movement["balance_amount"] == Decimal("-13")


def test_pdf_cuenta_corriente_banco_estado_tiene_un_unico_parser_en_registry(pdf_path):
    path = pdf_path("CARTOLA CTA CTE.pdf")
    matching_parsers = [
        parser.__class__.__name__
        for parser in get_available_parsers()
        if parser.can_parse(str(path))
    ]

    assert matching_parsers == ["BancoEstadoCuentaCorrienteParser"]
