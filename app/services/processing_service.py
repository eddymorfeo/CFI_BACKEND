from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

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
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Documento no encontrado.",
            )

        selected_parser = None
        for parser in get_available_parsers():
            if parser.can_parse(source_document.file_path):
                selected_parser = parser
                break

        if selected_parser is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No existe un parser compatible para este formato de documento.",
            )

        parsed_result = selected_parser.parse(source_document.file_path)

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
                branch=movement["branch"],
                description=movement["description"],
                document_number=movement["document_number"],
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

        source_document.detected_institution_name = document_metadata.get("detected_institution_name")
        source_document.detected_holder_name = document_metadata.get("detected_holder_name")
        source_document.detected_account_number = document_metadata.get("detected_account_number")
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