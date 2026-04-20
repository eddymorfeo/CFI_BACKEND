import uuid
from datetime import date

from sqlalchemy import Boolean, Date, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class ExtractedMovement(BaseModel):
    __tablename__ = "extracted_movements"
    __table_args__ = {"schema": "financial_ingestion"}

    extracted_movement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    source_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )

    processing_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )

    row_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)

    transaction_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_number: Mapped[str | None] = mapped_column(String(100), nullable=True)

    charge_amount: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    deposit_amount: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    balance_amount: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)

    raw_row_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_row_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    detected_movement_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_transfer_candidate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    confidence_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)