from decimal import Decimal
from pathlib import Path

import pytest

from app.parsers.banco_estado.cartola_instantanea_parser import (
    BancoEstadoCartolaInstantaneaParser,
)


def test_cartola_instantanea_multipagina_extrae_todos_los_movimientos():
    path = Path.home() / "Downloads" / "CARTOLA INSTANTANEA 1 1.pdf"
    if not path.exists():
        pytest.skip(f"No existe el PDF de prueba: {path}")

    parser = BancoEstadoCartolaInstantaneaParser()
    result = parser.parse(str(path))
    metadata = result["document_metadata"]

    assert parser.can_parse(str(path)) is True
    assert result["parser_code"] == "BANCO_ESTADO_CARTOLA_INSTANTANEA"
    assert len(result["movements"]) == 89
    assert metadata["document_date_from"].isoformat() == "2025-09-02"
    assert metadata["document_date_to"].isoformat() == "2025-09-30"

    first_movement = result["movements"][0]
    assert first_movement["description"] == "COMPRA NACIONAL HIP LIDER PU CL"
    assert first_movement["charge_amount"] == Decimal("1190")
    assert first_movement["deposit_amount"] == Decimal("0")
    assert first_movement["balance_amount"] == Decimal("240")
    assert first_movement["detected_movement_type"] == "PURCHASE"

    page_continuation_movement = result["movements"][19]
    assert page_continuation_movement["description"] == "TEF A MI CUENTA AHORRO 35563480317"
    assert page_continuation_movement["charge_amount"] == Decimal("4")
    assert page_continuation_movement["page_number"] == 2

    last_movement = result["movements"][-1]
    assert last_movement["transaction_date"].isoformat() == "2025-09-02"
    assert last_movement["description"] == "TRANSFERENCIA DESDE MIS CUENTAS"
    assert last_movement["deposit_amount"] == Decimal("182118")
