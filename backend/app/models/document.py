from __future__ import annotations

import uuid

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import DocumentType, check_in
from app.models.mixins import Timestamps, UUIDPk


class Document(UUIDPk, Timestamps, Base):
    """Métadonnées d'un document privé. Le binaire est dans le stockage objet (jamais en base)."""

    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(check_in("doc_type", DocumentType), name="doc_type_valid"),
        CheckConstraint("size_bytes > 0", name="size_positive"),
        CheckConstraint("version >= 1", name="version_positive"),
        UniqueConstraint("id", "user_id", name="uq_documents_id_user"),
        UniqueConstraint("user_id", "group_id", "version", name="uq_documents_group_version"),
        Index("ix_documents_user_type", "user_id", "doc_type"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    group_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    doc_type: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(400), nullable=False, unique=True)
    notes: Mapped[str | None] = mapped_column(Text)
