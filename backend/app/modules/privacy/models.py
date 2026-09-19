from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.identity.models import Base


class PrivacyDeletionRequest(Base):
    """Auditable local deletion request without claiming platform deletion."""

    __tablename__ = "privacy_deletion_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity_users.id", ondelete="CASCADE"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="LOCAL_COMPLETED")
    platform_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="NOT_REQUESTED"
    )
    scope: Mapped[dict] = mapped_column(JSONB, nullable=False)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("owner_user_id", "idempotency_key", name="uq_privacy_delete_owner_key"),
        CheckConstraint("status IN ('LOCAL_COMPLETED', 'FAILED')", name="ck_privacy_delete_status"),
        CheckConstraint(
            "platform_status IN ('NOT_REQUESTED', 'NOT_VERIFIED', 'PENDING_EXTERNAL', 'COMPLETED')",
            name="ck_privacy_delete_platform_status",
        ),
    )
