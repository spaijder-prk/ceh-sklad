from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from .models import MoneyOperation


class MoneyPostingRead(BaseModel):
    id: UUID
    representative_id: UUID
    representative_code: str
    representative_name: str
    document_id: UUID | None = None
    operation: MoneyOperation
    amount: Decimal
    comment: str | None = None
    external_id: str | None = None
    created_by_user_id: UUID | None = None
    created_by_name: str | None = None
    created_at: datetime
    reversed: bool = False
    reversed_by_user_id: UUID | None = None
    reversed_by_name: str | None = None
    reversed_at: datetime | None = None


class PaymentReverseResult(BaseModel):
    posting_id: UUID
    reversal_id: UUID
    debt_delta: Decimal
    already_reversed: bool
