from decimal import Decimal

from app.parsers.banco_chile.cuenta_corriente_estado_cuenta_parser import (
    BancoChileCuentaCorrienteEstadoCuentaParser,
)


def test_cuenta_corriente_andrea_tof_extrae_movimientos_y_fechas_reales(pdf_path):
    parser = BancoChileCuentaCorrienteEstadoCuentaParser()
    result = parser.parse(str(pdf_path("TOF-25000068 Andrea Sanhueza Álvarez cta cte OK.pdf")))

    dates = [
        movement["transaction_date"]
        for movement in result["movements"]
        if movement["transaction_date"] is not None
    ]

    assert result["parser_code"] == "BANCO_CHILE_CUENTA_CORRIENTE_ESTADO_CUENTA"
    assert len(result["movements"]) == 1035
    assert min(dates).isoformat() == "2022-01-06"
    assert max(dates).isoformat() == "2024-12-27"


def test_pago_proveedores_es_abono_en_cuenta_corriente(pdf_path):
    parser = BancoChileCuentaCorrienteEstadoCuentaParser()
    result = parser.parse(str(pdf_path("TOF-25000068 Andrea Sanhueza Álvarez cta cte OK.pdf")))

    provider_rows = [
        movement
        for movement in result["movements"]
        if "PAGO:PROVEEDORES" in movement["description"]
    ]

    assert len(provider_rows) == 14
    assert all(movement["charge_amount"] == Decimal("0") for movement in provider_rows)
    assert all(movement["deposit_amount"] > Decimal("0") for movement in provider_rows)
    assert all(movement["detected_movement_type"] == "DEPOSIT" for movement in provider_rows)
