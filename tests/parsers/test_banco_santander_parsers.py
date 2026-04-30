from decimal import Decimal

from app.parsers.banco_santander.cuenta_corriente_fan_parser import (
    BancoSantanderCuentaCorrienteFanParser,
)
from app.parsers.banco_santander.cuenta_mas_lucas_parser import (
    BancoSantanderCuentaMasLucasParser,
)
from app.parsers.parser_registry import get_available_parsers


def test_cuenta_corriente_fan_santander_extrae_movimientos_y_fechas(pdf_path):
    parser = BancoSantanderCuentaCorrienteFanParser()
    path = pdf_path("000-77-35262-7.pdf")

    result = parser.parse(str(path))

    assert parser.can_parse(str(path)) is True
    assert result["parser_code"] == "BANCO_SANTANDER_CUENTA_CORRIENTE_FAN"
    assert result["document_metadata"]["detected_institution_name"] == "Banco Santander"
    assert result["document_metadata"]["detected_holder_name"] == "BORQUEZ CATALAN PAULINA ELIANA"
    assert result["document_metadata"]["detected_account_number"] == "0-000-77-35262-7"
    assert result["document_metadata"]["document_date_from"].isoformat() == "2023-12-29"
    assert result["document_metadata"]["document_date_to"].isoformat() == "2025-01-31"
    assert len(result["movements"]) == 1065

    first_movement = result["movements"][0]
    assert first_movement["transaction_date"].isoformat() == "2024-01-02"
    assert first_movement["branch"] == "PLAZA SUR"
    assert first_movement["description"] == "00197214325 Dep Efect ATM 000000"
    assert first_movement["charge_amount"] == Decimal("0")
    assert first_movement["deposit_amount"] == Decimal("60000")

    purchase_row = result["movements"][2]
    assert purchase_row["description"] == "Compra Nacional NP VESTI INGENIERIA ONECL"
    assert purchase_row["document_number"] == "3365700"
    assert purchase_row["charge_amount"] == Decimal("64800")
    assert purchase_row["deposit_amount"] == Decimal("0")
    assert purchase_row["detected_movement_type"] == "PURCHASE"


def test_cuenta_mas_lucas_santander_extrae_movimientos_y_omite_cartola_sin_movimientos(pdf_path):
    parser = BancoSantanderCuentaMasLucasParser()
    path = pdf_path("CARTOLAS 5613913990.pdf")

    result = parser.parse(str(path))

    assert parser.can_parse(str(path)) is True
    assert result["parser_code"] == "BANCO_SANTANDER_CUENTA_MAS_LUCAS"
    assert result["document_metadata"]["detected_institution_name"] == "Banco Santander"
    assert result["document_metadata"]["detected_holder_name"] == "ALVAREZ FIGUEROA FERNANDO ANDRES"
    assert result["document_metadata"]["detected_account_number"] == "0-056-13-91399-0"
    assert result["document_metadata"]["document_date_from"].isoformat() == "2024-07-04"
    assert result["document_metadata"]["document_date_to"].isoformat() == "2024-09-30"
    assert len(result["movements"]) == 8

    first_movement = result["movements"][0]
    assert first_movement["transaction_date"].isoformat() == "2024-07-09"
    assert first_movement["document_number"] == "00141736582"
    assert first_movement["description"] == "Transf. VICTO"
    assert first_movement["charge_amount"] == Decimal("0")
    assert first_movement["deposit_amount"] == Decimal("1000")
    assert first_movement["balance_amount"] == Decimal("1000")

    interest_row = result["movements"][-1]
    assert interest_row["transaction_date"].isoformat() == "2024-09-01"
    assert interest_row["description"] == "Intereses Pagados"
    assert interest_row["deposit_amount"] == Decimal("2")
    assert interest_row["balance_amount"] == Decimal("1002")
    assert interest_row["detected_movement_type"] == "INTEREST"


def test_pdfs_santander_tienen_un_unico_parser_en_registry(pdf_path):
    expected_parsers = {
        "000-77-35262-7.pdf": "BancoSantanderCuentaCorrienteFanParser",
        "CARTOLAS 5613913990.pdf": "BancoSantanderCuentaMasLucasParser",
    }
    parsers = get_available_parsers()

    for file_name, expected_parser_name in expected_parsers.items():
        path = pdf_path(file_name)
        matching_parsers = [
            parser.__class__.__name__
            for parser in parsers
            if parser.can_parse(str(path))
        ]

        assert matching_parsers == [expected_parser_name]
