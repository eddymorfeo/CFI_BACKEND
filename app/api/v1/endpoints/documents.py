from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.schemas.document_schema import (
    SourceDocumentDetailResponse,
    SourceDocumentResponse,
)
from app.services.document_service import DocumentService
from app.services.processing_service import ProcessingService
from app.schemas.export_schema import ExportCartolaBancariaResponse
from app.services.export_service import ExportService
from fastapi.responses import FileResponse

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post(
    "/upload",
    response_model=SourceDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    file: UploadFile = File(...),
    database: Session = Depends(get_db),
):
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debe seleccionar un archivo.",
        )

    file_extension = Path(file.filename).suffix.lower()
    allowed_extensions = {".pdf", ".xlsx", ".xls", ".csv"}

    if file_extension not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tipo de archivo no permitido. Solo se aceptan PDF, XLSX, XLS y CSV.",
        )

    max_bytes = settings.max_file_size_mb * 1024 * 1024
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)

    if file_size > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El archivo supera el tamaño máximo permitido de {settings.max_file_size_mb} MB.",
        )

    return await DocumentService.upload_document(
        database=database,
        upload_file=file,
    )


@router.get(
    "",
    response_model=list[SourceDocumentResponse],
    status_code=status.HTTP_200_OK,
)
def list_documents(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    database: Session = Depends(get_db),
):
    return DocumentService.list_documents(database=database, skip=skip, limit=limit)


@router.get(
    "/{source_document_id}",
    response_model=SourceDocumentDetailResponse,
    status_code=status.HTTP_200_OK,
)
def get_document_detail(
    source_document_id: UUID,
    database: Session = Depends(get_db),
):
    return DocumentService.get_document_by_id(
        database=database,
        source_document_id=source_document_id,
    )

@router.post(
    "/{source_document_id}/process",
    status_code=status.HTTP_200_OK,
)
def process_document(
    source_document_id: UUID,
    database: Session = Depends(get_db),
):
    return ProcessingService.process_document(
        database=database,
        source_document_id=source_document_id,
    )
    

@router.get(
    "/{source_document_id}/export/cartola-bancaria",
    status_code=status.HTTP_200_OK,
)
def export_cartola_bancaria(
    source_document_id: UUID,
    database: Session = Depends(get_db),
):
    file_path = ExportService.generate_cartola_bancaria_file(
        database=database,
        source_document_id=source_document_id,
    )

    return FileResponse(
        path=file_path,
        media_type="text/csv",
        filename="formato_cartola_bancaria.csv",
    )
    

@router.delete(
    "/{source_document_id}",
    status_code=status.HTTP_200_OK,
)
def delete_document(
    source_document_id: UUID,
    database: Session = Depends(get_db),
):
    return DocumentService.delete_document(
        database=database,
        source_document_id=source_document_id,
    )