from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from .models import DocumentStatus, DocumentType


class DocumentLineRead(BaseModel):
    product_id: UUID
    sku: str
    product_name: str
    warehouse_id: UUID | None = None
    warehouse_name: str | None = None
    representative_id: UUID | None = None
    representative_name: str | None = None
    quantity: Decimal
    unit_price: Decimal | None = None


class DocumentRead(BaseModel):
    id: UUID
    document_type: DocumentType
    status: DocumentStatus
    external_id: str | None = None
    comment: str | None = None
    created_at: datetime
    posted_at: datetime
    updated_at: datetime
    sale_amount: Decimal = Decimal("0")
    lines: list[DocumentLineRead]


class DocumentCancelResult(BaseModel):
    document_id: UUID
    status: DocumentStatus
    stock_changed: bool
    debt_changed: bool
