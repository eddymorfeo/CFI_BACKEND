from app.services.export_service import ExportService
from app.services.processing_service import ProcessingService


def test_processing_service_normaliza_texto_a_mayusculas():
    assert ProcessingService._to_uppercase_text(" Pago:Proveedores 061606701k ") == "PAGO:PROVEEDORES 061606701K"
    assert ProcessingService._to_uppercase_text("Banco de Chile") == "BANCO DE CHILE"
    assert ProcessingService._to_uppercase_text(None) is None


def test_export_service_formatea_texto_en_mayusculas():
    assert ExportService._format_text(" Traspaso de cuenta:000265424239 ") == "TRASPASO DE CUENTA:000265424239"
    assert ExportService._format_text("Andrea Sanhueza") == "ANDREA SANHUEZA"
    assert ExportService._format_text(None) == ""
