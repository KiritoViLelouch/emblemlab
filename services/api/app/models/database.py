import os
from sqlalchemy import JSON, ForeignKeyConstraint, String, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class Game(Base):
    __tablename__ = "games"
    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))


class VersionedRecord(Base):
    """Typed discriminator + validated JSON payload; composite keys prohibit cross-game links."""

    __tablename__ = "versioned_records"
    game_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    ruleset_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    kind: Mapped[str] = mapped_column(String(60), primary_key=True)
    entity_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    patch: Mapped[str] = mapped_column(String(100))
    set_id: Mapped[str] = mapped_column(String(100))
    mode: Mapped[str] = mapped_column(String(100))
    source: Mapped[str] = mapped_column(String(300))
    imported_at: Mapped[str] = mapped_column(String(50))
    verification_status: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict] = mapped_column(JSON)


class EntityLink(Base):
    __tablename__ = "entity_links"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    game_id: Mapped[str] = mapped_column(String(20))
    ruleset_id: Mapped[str] = mapped_column(String(100))
    from_kind: Mapped[str] = mapped_column(String(60))
    from_id: Mapped[str] = mapped_column(String(100))
    to_kind: Mapped[str] = mapped_column(String(60))
    to_id: Mapped[str] = mapped_column(String(100))
    __table_args__ = (
        ForeignKeyConstraint(
            ["game_id", "ruleset_id", "from_kind", "from_id"],
            [
                "versioned_records.game_id",
                "versioned_records.ruleset_id",
                "versioned_records.kind",
                "versioned_records.entity_id",
            ],
        ),
        ForeignKeyConstraint(
            ["game_id", "ruleset_id", "to_kind", "to_id"],
            [
                "versioned_records.game_id",
                "versioned_records.ruleset_id",
                "versioned_records.kind",
                "versioned_records.entity_id",
            ],
        ),
    )


RECORD_KINDS = {
    "GameVersion",
    "Ruleset",
    "Champion",
    "Trait",
    "ChampionTrait",
    "Emblem",
    "EmblemEquipRule",
    "TraitThreshold",
    "TraitCountingRule",
    "ReforgeRule",
    "DataSource",
    "StatisticsObservation",
    "CommunityGuideRecommendation",
    "CrossGameEntityMapping",
}
engine = create_engine(os.getenv("DATABASE_URL", "sqlite:///./emblemlab.db"))
Session = sessionmaker(engine)


if engine.dialect.name == "sqlite":

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")
