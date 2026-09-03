from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class IntegrationExportLink(Base):
    """Связь одной операции ceh-sklad с одним из созданных внешних документов.

    `entity_internal_id` намеренно не является FK: экспортируемый объект может быть
    как stock_document, так и другой сущностью. Тип задается `entity_type`.
    """

    __tablename__ = "integration_export_links"
    __table_args__ = (
        UniqueConstraint(
            "entity_type",
            "external_1c_id",
            name="uq_integration_export_links_entity_external",
        ),
        UniqueConstraint(
            "entity_type",
            "entity_internal_id",
            "external_1c_id",
            name="uq_integration_export_links_internal_external",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    entity_type: Mapped[str] = mapped_column(String(50), index=True)
    entity_internal_id: Mapped[UUID] = mapped_column(index=True)
    external_1c_id: Mapped[str] = mapped_column(String(100), index=True)
    external_kind: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
