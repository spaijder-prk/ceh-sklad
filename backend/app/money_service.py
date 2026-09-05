from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import MoneyOperation, MoneyPosting, Representative
from .money_schemas import MoneyPostingRead, PaymentReverseResult
from .services import ConflictError, NotFoundError


REVERSAL_PREFIX = "reverse-payment-"


def money_journal(session: Session, limit: int = 100) -> list[MoneyPostingRead]:
    rows = session.execute(
        select(MoneyPosting, Representative)
        .join(Representative, Representative.id == MoneyPosting.representative_id)
        .order_by(MoneyPosting.created_at.desc(), MoneyPosting.id.desc())
        .limit(limit)
    ).all()
    reversal_ids = set(
        session.scalars(
            select(MoneyPosting.external_id).where(
                MoneyPosting.external_id.like(f"{REVERSAL_PREFIX}%")
            )
        ).all()
    )
    return [
        MoneyPostingRead(
            id=posting.id,
            representative_id=representative.id,
            representative_code=representative.code,
            representative_name=representative.name,
            document_id=posting.document_id,
            operation=posting.operation,
            amount=posting.amount,
            comment=posting.comment,
            external_id=posting.external_id,
            created_at=posting.created_at,
            reversed=f"{REVERSAL_PREFIX}{posting.id}" in reversal_ids,
        )
        for posting, representative in rows
    ]


def reverse_payment(session: Session, posting_id: UUID) -> PaymentReverseResult:
    posting = session.scalar(
        select(MoneyPosting).where(MoneyPosting.id == posting_id).with_for_update()
    )
    if posting is None:
        raise NotFoundError("Денежная проводка не найдена")
    if posting.operation != MoneyOperation.PAYMENT:
        raise ConflictError("Через этот маршрут можно сторнировать только сдачу денег")

    external_id = f"{REVERSAL_PREFIX}{posting.id}"
    existing = session.scalar(
        select(MoneyPosting).where(MoneyPosting.external_id == external_id)
    )
    if existing is not None:
        return PaymentReverseResult(
            posting_id=posting.id,
            reversal_id=existing.id,
            debt_delta=Decimal(existing.amount),
            already_reversed=True,
        )

    reversal = MoneyPosting(
        representative_id=posting.representative_id,
        document_id=None,
        operation=MoneyOperation.ADJUSTMENT,
        amount=-Decimal(posting.amount),
        comment=f"Сторно сдачи денег {posting.id}",
        external_id=external_id,
    )
    session.add(reversal)
    session.commit()
    session.refresh(reversal)
    return PaymentReverseResult(
        posting_id=posting.id,
        reversal_id=reversal.id,
        debt_delta=Decimal(reversal.amount),
        already_reversed=False,
    )
