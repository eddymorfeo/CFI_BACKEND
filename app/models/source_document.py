import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class SourceDocument(BaseModel):
    __tablename__ = "source_documents"
    __table_args__ = {"schema": "financial_ingestion"}

    source_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    original_file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_extension: Mapped[str] = mapped_column(String(20), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(nullable=True)
    file_hash_sha256: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    institution_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    holder_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    financial_product_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    document_type_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    product_type_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    detected_institution_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    detected_holder_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    detected_account_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    detected_currency_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    detected_document_number: Mapped[str | None] = mapped_column(String(100), nullable=True)

    document_date_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    document_date_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    document_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)

    processing_status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING")
    review_status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING")
    source_origin: Mapped[str] = mapped_column(String(30), nullable=False, default="MANUAL_UPLOAD")

    parser_code: Mapped[str | None] = mapped_column(String(255), nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_text_extracted: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_json_extracted: Mapped[dict | None] = mapped_column(JSONB, nullable=True)