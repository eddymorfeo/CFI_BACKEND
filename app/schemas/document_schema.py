from pydantic import BaseModel
from uuid import UUID
from datetime import datetime, date


class SourceDocumentResponse(BaseModel):
    source_document_id: UUID
    original_file_name: str
    stored_file_name: str
    file_path: str
    file_extension: str
    mime_type: str | None = None
    file_size_bytes: int | None = None
    uploaded_at: datetime
    processing_status: str
    review_status: str
    source_origin: str

    detected_institution_name: str | None = None
    detected_document_group: str | None = None
    detected_document_type: str | None = None

    class Config:
        from_attributes = True


class SourceDocumentDetailResponse(BaseModel):
    source_document_id: UUID
    original_file_name: str
    stored_file_name: str
    file_path: str
    file_extension: str
    mime_type: str | None = None
    file_size_bytes: int | None = None
    uploaded_at: datetime
    processing_status: str
    review_status: str
    source_origin: str

    detected_institution_name: str | None = None
    detected_holder_name: str | None = None
    detected_account_number: str | None = None
    document_date_from: date | None = None
    document_date_to: date | None = None

    detected_document_group: str | None = None
    detected_document_type: str | None = None

    class Config:
        from_attributes = True