"""Immutable provider observations, physically separate from community opinion."""

from sqlalchemy import JSON, Index, String
from sqlalchemy.orm import Mapped, mapped_column
from app.models.database import Base


class StatisticsRecord(Base):
    __tablename__ = "statistics_observations"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider_id: Mapped[str] = mapped_column(String(300))
    provider_record_id: Mapped[str] = mapped_column(String(300))
    game_id: Mapped[str] = mapped_column(String(20))
    ruleset_id: Mapped[str] = mapped_column(String(300))
    patch: Mapped[str] = mapped_column(String(300))
    set_id: Mapped[str] = mapped_column(String(300))
    mode: Mapped[str] = mapped_column(String(300))
    data_kind: Mapped[str] = mapped_column(String(20))
    context_kind: Mapped[str] = mapped_column(String(20))
    context_key: Mapped[str] = mapped_column(String(64))
    payload_sha256: Mapped[str] = mapped_column(String(64))
    catalog_sha256: Mapped[str] = mapped_column(String(64))
    imported_at: Mapped[str] = mapped_column(String(50))
    authorization: Mapped[dict] = mapped_column(JSON)
    observation: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (Index("ix_statistics_scope", "game_id", "ruleset_id", "patch", "set_id", "mode", "data_kind"),)
