from datetime import datetime, timezone
from pathlib import Path

from fastapi import UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppException
from app.models.extracted_movement import ExtractedMovement
from app.models.source_document import SourceDocument
from app.services.document_classifier_service import DocumentClassifierService
from app.utils.file_utils import save_upload_file


class DocumentService:
    @staticmethod
    async def upload_document(database: Session, upload_file: UploadFile) -> SourceDocument:
        file_path, stored_file_name, file_size_bytes, file_hash_sha256 = await save_upload_file(upload_file)

        source_document = SourceDocument(
            original_file_name=upload_file.filename,
            stored_file_name=stored_file_name,
            file_path=file_path,
            file_extension=Path(upload_file.filename).suffix.lower(),
            mime_type=upload_file.content_type,
            file_size_bytes=file_size_bytes,
            file_hash_sha256=file_hash_sha256,
            uploaded_at=datetime.now(timezone.utc),
            processing_status="PENDING",
            review_status="PENDING",
            source_origin="MANUAL_UPLOAD",
        )

        try:
            database.add(source_document)
            database.commit()
            database.refresh(source_document)
        except IntegrityError:
            database.rollback()
            raise AppException(
                error_code="DOCUMENT_ALREADY_EXISTS",
                message="Este archivo ya fue cargado anteriormente.",
                detail=f"El archivo '{upload_file.filename}' ya existe en la plataforma.",
                status_code=status.HTTP_409_CONFLICT,
                context={"original_file_name": upload_file.filename},
            )

        return source_document

    @staticmethod
    def list_documents(database: Session, skip: int = 0, limit: int = 50):
        documents = (
            database.query(SourceDocument)
            .order_by(SourceDocument.uploaded_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

        response = []
        for document in documents:
            parser_code = getattr(document, "parser_code", None)
            response.append(
                {
                    "source_document_id": document.source_document_id,
                    "original_file_name": document.original_file_name,
                    "stored_file_name": document.stored_file_name,
                    "file_path": document.file_path,
                    "file_extension": document.file_extension,
                    "mime_type": document.mime_type,
                    "file_size_bytes": document.file_size_bytes,
                    "uploaded_at": document.uploaded_at,
                    "processing_status": document.processing_status,
                    "review_status": document.review_status,
                    "source_origin": document.source_origin,
                    "detected_institution_name": getattr(document, "detected_institution_name", None),
                    "detected_document_group": DocumentClassifierService.detect_document_group(parser_code),
                    "detected_document_type": DocumentClassifierService.detect_document_type(parser_code),
                }
            )

        return response

    @staticmethod
    def get_document_by_id(database: Session, source_document_id):
        document = (
            database.query(SourceDocument)
            .filter(SourceDocument.source_document_id == source_document_id)
            .first()
        )

        if document is None:
            raise AppException(
                error_code="DOCUMENT_NOT_FOUND",
                message="No encontramos el documento solicitado.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        parser_code = getattr(document, "parser_code", None)

        return {
            "source_document_id": document.source_document_id,
            "original_file_name": document.original_file_name,
            "stored_file_name": document.stored_file_name,
            "file_path": document.file_path,
            "file_extension": document.file_extension,
            "mime_type": document.mime_type,
            "file_size_bytes": document.file_size_bytes,
            "uploaded_at": document.uploaded_at,
            "processing_status": document.processing_status,
            "review_status": document.review_status,
            "source_origin": document.source_origin,
            "detected_institution_name": getattr(document, "detected_institution_name", None),
            "detected_holder_name": getattr(document, "detected_holder_name", None),
            "detected_account_number": getattr(document, "detected_account_number", None),
            "document_date_from": getattr(document, "document_date_from", None),
            "document_date_to": getattr(document, "document_date_to", None),
            "detected_document_group": DocumentClassifierService.detect_document_group(parser_code),
            "detected_document_type": DocumentClassifierService.detect_document_type(parser_code),
        }

    @staticmethod
    def delete_document(database: Session, source_document_id):
        document = (
            database.query(SourceDocument)
            .filter(SourceDocument.source_document_id == source_document_id)
            .first()
        )

        if document is None:
            raise AppException(
                error_code="DOCUMENT_NOT_FOUND",
                message="No se pudo eliminar porque el documento no existe.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        database.query(ExtractedMovement).filter(
            ExtractedMovement.source_document_id == source_document_id
        ).delete(synchronize_session=False)

        stored_file_path = Path(document.file_path)

        database.delete(document)
        database.commit()

        if stored_file_path.exists():
            try:
                stored_file_path.unlink()
            except Exception:
                pass

        return {"message": "Documento eliminado correctamente."}