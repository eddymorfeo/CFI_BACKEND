import hashlib
from datetime import datetime, timezone
from pathlib import Path

from fastapi import UploadFile, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppException
from app.models.extracted_movement import ExtractedMovement
from app.models.source_document import SourceDocument
from app.services.document_classifier_service import DocumentClassifierService
from app.utils.file_utils import save_upload_content


class DocumentService:
    @staticmethod
    async def upload_document(database: Session, upload_file: UploadFile) -> SourceDocument:
        content = await upload_file.read()
        file_hash_sha256 = hashlib.sha256(content).hexdigest()
        existing_document = DocumentService._get_document_by_hash(database, file_hash_sha256)

        if existing_document is not None:
            raise DocumentService._build_duplicate_document_exception(
                upload_file_name=upload_file.filename,
                existing_document=existing_document,
            )

        file_path, stored_file_name, file_size_bytes, file_hash_sha256 = save_upload_content(
            original_file_name=upload_file.filename,
            content=content,
        )

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
            Path(file_path).unlink(missing_ok=True)
            existing_document = DocumentService._get_document_by_hash(database, file_hash_sha256)

            if existing_document is not None:
                raise DocumentService._build_duplicate_document_exception(
                    upload_file_name=upload_file.filename,
                    existing_document=existing_document,
                )

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

        document_ids = [document.source_document_id for document in documents]
        movements_count_by_document_id = DocumentService._count_extracted_movements_by_document_id(
            database=database,
            source_document_ids=document_ids,
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
                    "extracted_movements_count": movements_count_by_document_id.get(
                        document.source_document_id,
                        0,
                    ),
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
        extracted_movements_count = (
            database.query(func.count(ExtractedMovement.extracted_movement_id))
            .filter(ExtractedMovement.source_document_id == source_document_id)
            .scalar()
        )

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
            "extracted_movements_count": extracted_movements_count or 0,
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

    @staticmethod
    def _count_extracted_movements_by_document_id(
        database: Session,
        source_document_ids,
    ) -> dict:
        if not source_document_ids:
            return {}

        rows = (
            database.query(
                ExtractedMovement.source_document_id,
                func.count(ExtractedMovement.extracted_movement_id),
            )
            .filter(ExtractedMovement.source_document_id.in_(source_document_ids))
            .group_by(ExtractedMovement.source_document_id)
            .all()
        )

        return {
            source_document_id: movements_count
            for source_document_id, movements_count in rows
        }

    @staticmethod
    def _get_document_by_hash(database: Session, file_hash_sha256: str) -> SourceDocument | None:
        return (
            database.query(SourceDocument)
            .filter(SourceDocument.file_hash_sha256 == file_hash_sha256)
            .first()
        )

    @staticmethod
    def _build_duplicate_document_exception(
        upload_file_name: str,
        existing_document: SourceDocument,
    ) -> AppException:
        detail = (
            f"Este PDF ya fue cargado anteriormente como "
            f"'{existing_document.original_file_name}'."
        )

        return AppException(
            error_code="DOCUMENT_ALREADY_EXISTS",
            message="Este documento ya existe por contenido.",
            detail=detail,
            status_code=status.HTTP_409_CONFLICT,
            context={
                "original_file_name": upload_file_name,
                "existing_source_document_id": str(existing_document.source_document_id),
                "existing_original_file_name": existing_document.original_file_name,
                "existing_uploaded_at": existing_document.uploaded_at.isoformat()
                if existing_document.uploaded_at is not None
                else None,
            },
        )
