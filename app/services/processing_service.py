from uuid import UUID

from sqlalchemy.orm import Session
from fastapi import status

from app.core.errors import AppException
from app.models.extracted_movement import ExtractedMovement
from app.models.source_document import SourceDocument
from app.parsers.parser_registry import get_available_parsers


class ProcessingService:
    @staticmethod
    def process_document(database: Session, source_document_id: UUID) -> dict:
        source_document = (
            database.query(SourceDocument)
            .filter(SourceDocument.source_document_id == source_document_id)
            .first()
        )

        if source_document is None:
            raise AppException(
                error_code="DOCUMENT_NOT_FOUND",
                message="No encontramos el documento que intentas procesar.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        selected_parser = None

        for parser in get_available_parsers():
            if parser.can_parse(source_document.file_path):
                selected_parser = parser
                break

        if selected_parser is None:
            source_document.processing_status = "FAILED"
            database.commit()

            raise AppException(
                error_code="UNSUPPORTED_DOCUMENT_FORMAT",
                message="No pudimos reconocer el formato de esta cartola.",
                detail="No existe un parser compatible para este documento.",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                context={"original_file_name": source_document.original_file_name},
            )

        try:
            parsed_result = selected_parser.parse(source_document.file_path)
        except Exception as exception:
            source_document.processing_status = "FAILED"
            database.commit()

            raise AppException(
                error_code="DOCUMENT_PROCESSING_FAILED",
                message="El documento se cargó, pero falló su procesamiento.",
                detail=str(exception),
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                context={"original_file_name": source_document.original_file_name},
            )

        database.query(ExtractedMovement).filter(
            ExtractedMovement.source_document_id == source_document_id
        ).delete(synchronize_session=False)

        for movement in parsed_result["movements"]:
            extracted_movement = ExtractedMovement(
                source_document_id=source_document_id,
                processing_run_id=None,
                row_number=movement["row_number"],
                page_number=movement["page_number"],
                transaction_date=movement["transaction_date"],
                branch=ProcessingService._to_uppercase_text(movement["branch"]),
                description=ProcessingService._to_uppercase_text(movement["description"]),
                document_number=ProcessingService._to_uppercase_text(movement["document_number"]),
                charge_amount=movement["charge_amount"],
                deposit_amount=movement["deposit_amount"],
                balance_amount=movement["balance_amount"],
                raw_row_text=movement["raw_row_text"],
                raw_row_json=movement["raw_row_json"],
                detected_movement_type=movement["detected_movement_type"],
                is_transfer_candidate=movement["is_transfer_candidate"],
                confidence_score=movement["confidence_score"],
            )
            database.add(extracted_movement)

        document_metadata = parsed_result.get("document_metadata", {})

        if hasattr(source_document, "parser_code"):
            source_document.parser_code = parsed_result.get("parser_code")

        source_document.detected_institution_name = ProcessingService._to_uppercase_text(
            document_metadata.get("detected_institution_name")
        )
        source_document.detected_holder_name = ProcessingService._to_uppercase_text(
            document_metadata.get("detected_holder_name")
        )
        source_document.detected_account_number = ProcessingService._to_uppercase_text(
            document_metadata.get("detected_account_number")
        )
        source_document.document_date_from = document_metadata.get("document_date_from")
        source_document.document_date_to = document_metadata.get("document_date_to")
        source_document.processing_status = "PROCESSED"

        database.commit()
        database.refresh(source_document)

        return {
            "source_document_id": str(source_document_id),
            "parser_code": parsed_result["parser_code"],
            "movements_count": len(parsed_result["movements"]),
            "status": "processed",
        }

    @staticmethod
    def _to_uppercase_text(value):
        if value is None:
            return None

        normalized_value = str(value).strip()
        if not normalized_value:
            return ""

        return normalized_value.upper()
