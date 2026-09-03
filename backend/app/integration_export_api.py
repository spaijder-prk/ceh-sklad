from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_session
from .integration_1c import require_1c_key
from .integration_export import IntegrationExportLink
from .models import IntegrationExchangeLog, MoneyTransaction, StockDocument, StockDocumentKind


router = APIRouter(
    prefix="/api/v1/integration/1c",
    tags=["Подтверждение экспорта 1С"],
    dependencies=[Depends(require_1c_key)],
)


class ExportDocumentConfirmation(BaseModel):
    external_1c_id: str = Field(min_length=1, max_length=100)
    external_kind: str | None = Field(default=None, min_length=1, max_length=100)


class ConfirmExportBatchIn(BaseModel):
    entity_type: Literal["stock_document"]
    internal_id: UUID
    documents: list[ExportDocumentConfirmation] = Field(min_length=1, max_length=2)


class ConfirmExportBatchOut(BaseModel):
    internal_id: UUID
    external_1c_ids: list[str]
    repeated: bool = False


def _payload_hash(payload: BaseModel) -> str:
    raw = json.dumps(payload.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def _ensure_external_ids_are_free(
    session: AsyncSession,
    entity_type: str,
    internal_id: UUID,
    external_ids: set[str],
) -> None:
    linked = list(
        await session.scalars(
            select(IntegrationExportLink).where(
                IntegrationExportLink.entity_type == entity_type,
                IntegrationExportLink.external_1c_id.in_(external_ids),
            )
        )
    )
    if any(row.entity_internal_id != internal_id for row in linked):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Один из идентификаторов УНФ уже связан с другой операцией",
        )

    legacy_stock = await session.scalar(
        select(StockDocument.id).where(
            StockDocument.external_1c_id.in_(external_ids),
            StockDocument.id != internal_id,
        )
    )
    legacy_money = await session.scalar(
        select(MoneyTransaction.id).where(MoneyTransaction.external_1c_id.in_(external_ids))
    )
    if legacy_stock is not None or legacy_money is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Один из идентификаторов УНФ уже используется ранее подтвержденным объектом",
        )


@router.post("/confirm-export-batch", response_model=ConfirmExportBatchOut)
async def confirm_export_batch(
    payload: ConfirmExportBatchIn,
    session: AsyncSession = Depends(get_session),
) -> ConfirmExportBatchOut:
    document = await session.get(StockDocument, payload.internal_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Складской документ экспорта не найден")

    if len(payload.documents) > 1 and document.kind != StockDocumentKind.ADJUSTMENT:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Несколько документов УНФ разрешены только для корректировки, требующей разделения",
        )

    requested = {(item.external_1c_id, item.external_kind) for item in payload.documents}
    if len(requested) != len(payload.documents):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Список подтверждений содержит повторяющийся документ УНФ",
        )

    existing_links = list(
        await session.scalars(
            select(IntegrationExportLink)
            .where(
                IntegrationExportLink.entity_type == payload.entity_type,
                IntegrationExportLink.entity_internal_id == payload.internal_id,
            )
            .order_by(IntegrationExportLink.external_1c_id)
        )
    )
    existing = {(row.external_1c_id, row.external_kind) for row in existing_links}
    if existing:
        if existing != requested:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Операция уже подтверждена другим набором документов УНФ",
            )
        if document.synced_1c_at is None:
            document.synced_1c_at = datetime.now(UTC)
            await session.commit()
        return ConfirmExportBatchOut(
            internal_id=document.id,
            external_1c_ids=sorted(row.external_1c_id for row in existing_links),
            repeated=True,
        )

    if document.external_1c_id is not None:
        if len(payload.documents) == 1 and document.external_1c_id == payload.documents[0].external_1c_id:
            return ConfirmExportBatchOut(
                internal_id=document.id,
                external_1c_ids=[document.external_1c_id],
                repeated=True,
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Операция уже подтверждена одиночным идентификатором 1С",
        )

    external_ids = {item.external_1c_id for item in payload.documents}
    await _ensure_external_ids_are_free(session, payload.entity_type, payload.internal_id, external_ids)

    now = datetime.now(UTC)
    for item in payload.documents:
        session.add(
            IntegrationExportLink(
                entity_type=payload.entity_type,
                entity_internal_id=document.id,
                external_1c_id=item.external_1c_id,
                external_kind=item.external_kind,
            )
        )

    if len(payload.documents) == 1:
        document.external_1c_id = payload.documents[0].external_1c_id
    document.synced_1c_at = now

    operation_key = f"confirm-batch:{payload.entity_type}:{payload.internal_id}"
    payload_hash = _payload_hash(payload)
    log = await session.scalar(select(IntegrationExchangeLog).where(IntegrationExchangeLog.operation_key == operation_key))
    if log is None:
        log = IntegrationExchangeLog(
            direction="outbound",
            operation_key=operation_key,
            entity_type=payload.entity_type,
            entity_internal_id=document.id,
            external_1c_id=payload.documents[0].external_1c_id if len(payload.documents) == 1 else None,
            payload_hash=payload_hash,
            status="completed",
            payload=payload.model_dump(mode="json"),
            completed_at=now,
        )
        session.add(log)
    else:
        if log.payload_hash != payload_hash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Пакет подтверждения уже использован с другим набором документов УНФ",
            )
        log.status = "completed"
        log.payload = payload.model_dump(mode="json")
        log.completed_at = now

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Идентификатор УНФ уже связан с другой операцией",
        ) from exc

    return ConfirmExportBatchOut(
        internal_id=document.id,
        external_1c_ids=sorted(external_ids),
    )
