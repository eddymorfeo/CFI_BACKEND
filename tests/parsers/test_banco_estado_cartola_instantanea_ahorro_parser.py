from decimal import Decimal

from app.parsers.banco_estado.cartola_instantanea_ahorro_parser import (
    BancoEstadoCartolaInstantaneaAhorroParser,
)
from app.parsers.banco_estado.cartola_instantanea_parser import BancoEstadoCartolaInstantaneaParser
from app.parsers.parser_registry import get_available_parsers


def test_cartola_instantanea_ahorro_extrae_movimientos_y_metadata(pdf_path):
    parser = BancoEstadoCartolaInstantaneaAhorroParser()
    path = pdf_path("CARTOL~1 1.PDF")

    result = parser.parse(str(path))

    assert parser.can_parse(str(path)) is True
    assert result["parser_code"] == "BANCO_ESTADO_AHORRO_CARTOLA_INSTANTANEA"
    assert result["document_metadata"]["detected_institution_name"] == "BancoEstado"
    assert result["document_metadata"]["detected_holder_name"] == "VERGARA ROJAS NATHALY ALEJANDRA"
    assert result["document_metadata"]["detected_holder_rut"] == "17.049.137-8"
    assert result["document_metadata"]["detected_account_number"] == "35662295661"
    assert result["document_metadata"]["detected_account_type"] == "VISTA PENSION ALIMENTICIA"
    assert result["document_metadata"]["document_issue_date"].isoformat() == "2025-12-26"
    assert result["document_metadata"]["document_date_from"].isoformat() == "2025-11-24"
    assert result["document_metadata"]["document_date_to"].isoformat() == "2025-12-15"
    assert len(result["movements"]) == 8

    first_movement = result["movements"][0]
    assert first_movement["transaction_date"].isoformat() == "2025-11-24"
    assert first_movement["branch"] == "001"
    assert first_movement["description"] == "DEP EN EFECTIVO SIN LIBRETA"
    assert first_movement["charge_amount"] == Decimal("0")
    assert first_movement["deposit_amount"] == Decimal("30000")
    assert first_movement["balance_amount"] == Decimal("30000")
    assert first_movement["detected_movement_type"] == "DEPOSIT"

    transfer_in = result["movements"][5]
    assert transfer_in["description"] == "DEP POR TRANSFERENCIA"
    assert transfer_in["deposit_amount"] == Decimal("50000")
    assert transfer_in["detected_movement_type"] == "TRANSFER_IN"

    last_movement = result["movements"][-1]
    assert last_movement["description"] == "GIRO POR TRANSFERENCIA"
    assert last_movement["charge_amount"] == Decimal("48000")
    assert last_movement["balance_amount"] == Decimal("0")
    assert last_movement["detected_movement_type"] == "TRANSFER_OUT"


def test_cartola_instantanea_ahorro_no_la_toma_el_parser_instantaneo_anterior(pdf_path):
    path = pdf_path("CARTOL~1 1.PDF")

    assert BancoEstadoCartolaInstantaneaParser().can_parse(str(path)) is False


def test_pdf_cartola_instantanea_ahorro_tiene_un_unico_parser_en_registry(pdf_path):
    path = pdf_path("CARTOL~1 1.PDF")
    matching_parsers = [
        parser.__class__.__name__
        for parser in get_available_parsers()
        if parser.can_parse(str(path))
    ]

    assert matching_parsers == ["BancoEstadoCartolaInstantaneaAhorroParser"]
