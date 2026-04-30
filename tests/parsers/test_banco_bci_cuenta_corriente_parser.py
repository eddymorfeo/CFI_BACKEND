from decimal import Decimal

from app.parsers.banco_bci.cuenta_corriente_parser import BancoBciCuentaCorrienteParser
from app.parsers.parser_registry import get_available_parsers


def test_cuenta_corriente_bci_extrae_movimientos_y_metadata(pdf_path):
    parser = BancoBciCuentaCorrienteParser()
    path = pdf_path("Cartola  cta 49888609 BCI.pdf")

    result = parser.parse(str(path))

    assert parser.can_parse(str(path)) is True
    assert result["parser_code"] == "BANCO_BCI_CARTOLA_CUENTA_CORRIENTE"
    assert result["document_metadata"]["detected_institution_name"] == "BCI"
    assert result["document_metadata"]["detected_holder_name"] == "NATHALY ALEJANDRA VERGARA ROJAS"
    assert result["document_metadata"]["detected_account_number"] == "49888609"
    assert result["document_metadata"]["detected_account_type"] == "CUENTA CORRIENTE"
    assert result["document_metadata"]["document_date_from"].isoformat() == "2022-10-24"
    assert result["document_metadata"]["document_date_to"].isoformat() == "2023-12-29"
    assert len(result["movements"]) == 24

    first_movement = result["movements"][0]
    assert first_movement["transaction_date"].isoformat() == "2022-10-24"
    assert first_movement["branch"] == "OF CENTRA"
    assert first_movement["description"] == "TRANSFER DE ALVARO JAVIER"
    assert first_movement["document_number"] == "369818959"
    assert first_movement["charge_amount"] == Decimal("0")
    assert first_movement["deposit_amount"] == Decimal("590000")
    assert first_movement["balance_amount"] == Decimal("590000")
    assert first_movement["detected_movement_type"] == "TRANSFER_IN"

    second_movement = result["movements"][1]
    assert second_movement["description"] == "TRANSFER A N.VERGARA ROJA"
    assert second_movement["charge_amount"] == Decimal("590000")
    assert second_movement["deposit_amount"] == Decimal("0")
    assert second_movement["balance_amount"] == Decimal("0")
    assert second_movement["detected_movement_type"] == "TRANSFER_OUT"


def test_pdf_bci_tiene_un_unico_parser_en_registry(pdf_path):
    path = pdf_path("Cartola  cta 49888609 BCI.pdf")
    matching_parsers = [
        parser.__class__.__name__
        for parser in get_available_parsers()
        if parser.can_parse(str(path))
    ]

    assert matching_parsers == ["BancoBciCuentaCorrienteParser"]
