import csv
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.extracted_movement import ExtractedMovement
from app.models.source_document import SourceDocument
from app.utils.export_utils import ensure_export_directory_exists


class ExportService:
    @staticmethod
    def generate_cartola_bancaria_file(database: Session, source_document_id: UUID) -> str:
        source_document = (
            database.query(SourceDocument)
            .filter(SourceDocument.source_document_id == source_document_id)
            .first()
        )

        if source_document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Documento no encontrado.",
            )

        extracted_movements = (
            database.query(ExtractedMovement)
            .filter(ExtractedMovement.source_document_id == source_document_id)
            .order_by(ExtractedMovement.row_number.asc())
            .all()
        )

        if not extracted_movements:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El documento no tiene movimientos extraídos para exportar.",
            )

        export_directory = ensure_export_directory_exists()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_name = f"formato_cartola_bancaria_{source_document_id}_{timestamp}.csv"
        file_path = export_directory / file_name

        with open(file_path, mode="w", newline="", encoding="utf-8-sig") as csv_file:
            writer = csv.writer(csv_file, delimiter=";")

            writer.writerow(
                [
                    "fecha",
                    "sucursal",
                    "descripcion",
                    "n_documento",
                    "cargo",
                    "abono",
                    "clasificacion",
                ]
            )

            for movement in extracted_movements:
                writer.writerow(
                    [
                        ExportService._format_date(movement.transaction_date),
                        "",
                        ExportService._format_text(movement.description),
                        ExportService._format_text(movement.document_number),
                        ExportService._format_amount(movement.charge_amount),
                        ExportService._format_amount(movement.deposit_amount),
                        "",
                    ]
                )

        return str(file_path)

    @staticmethod
    def _format_date(transaction_date) -> str:
        if transaction_date is None:
            return ""
        return transaction_date.strftime("%d-%m-%Y")

    @staticmethod
    def _format_amount(amount) -> str:
        if amount is None:
            return "0"

        if isinstance(amount, Decimal):
            normalized_amount = amount.quantize(Decimal("1"))
            return str(normalized_amount)

        return str(int(amount))

    @staticmethod
    def _format_text(value) -> str:
        if value is None:
            return ""

        return str(value).strip().upper()
