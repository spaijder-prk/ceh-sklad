from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .models import utcnow


class OneCEntityType(StrEnum):
    WAREHOUSE = "warehouse"
    PRODUCT = "product"
    REPRESENTATIVE = "representative"


class OneCEntityLink(Base):
    __tablename__ = "one_c_entity_links"
    __table_args__ = (
        UniqueConstraint(
            "entity_type",
            "backend_id",
            name="uq_one_c_entity_links_backend",
        ),
        UniqueConstraint(
            "entity_type",
            "external_ref",
            name="uq_one_c_entity_links_external_ref",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    entity_type: Mapped[OneCEntityType] = mapped_column(String(32), index=True)
    backend_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    external_ref: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
