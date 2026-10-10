"""Community opinions are stored separately from catalog and statistical observations."""

from sqlalchemy import JSON, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from app.models.database import Base


class GuideImport(Base):
    __tablename__ = "community_imports"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    metadata_json: Mapped[dict] = mapped_column(JSON)


class GuideRow(Base):
    __tablename__ = "community_rows"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    import_id: Mapped[str] = mapped_column(ForeignKey("community_imports.id"), index=True)
    row_number: Mapped[int] = mapped_column(Integer)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    raw: Mapped[dict] = mapped_column(JSON)
    current: Mapped[dict] = mapped_column(JSON)
    history: Mapped[list] = mapped_column(JSON, default=list)
