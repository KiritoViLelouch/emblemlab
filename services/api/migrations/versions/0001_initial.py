"""Initial versioned entity store. Frozen schema for revision 0001."""

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "games", sa.Column("id", sa.String(20), primary_key=True), sa.Column("name", sa.String(200), nullable=False)
    )
    op.create_table(
        "versioned_records",
        sa.Column("game_id", sa.String(20), primary_key=True),
        sa.Column("ruleset_id", sa.String(100), primary_key=True),
        sa.Column("kind", sa.String(60), primary_key=True),
        sa.Column("entity_id", sa.String(100), primary_key=True),
        sa.Column("patch", sa.String(100), nullable=False),
        sa.Column("set_id", sa.String(100), nullable=False),
        sa.Column("mode", sa.String(100), nullable=False),
        sa.Column("source", sa.String(300), nullable=False),
        sa.Column("imported_at", sa.String(50), nullable=False),
        sa.Column("verification_status", sa.String(50), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_table(
        "entity_links",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column("game_id", sa.String(20), nullable=False),
        sa.Column("ruleset_id", sa.String(100), nullable=False),
        sa.Column("from_kind", sa.String(60), nullable=False),
        sa.Column("from_id", sa.String(100), nullable=False),
        sa.Column("to_kind", sa.String(60), nullable=False),
        sa.Column("to_id", sa.String(100), nullable=False),
        sa.ForeignKeyConstraint(
            ["game_id", "ruleset_id", "from_kind", "from_id"],
            [
                "versioned_records.game_id",
                "versioned_records.ruleset_id",
                "versioned_records.kind",
                "versioned_records.entity_id",
            ],
        ),
        sa.ForeignKeyConstraint(
            ["game_id", "ruleset_id", "to_kind", "to_id"],
            [
                "versioned_records.game_id",
                "versioned_records.ruleset_id",
                "versioned_records.kind",
                "versioned_records.entity_id",
            ],
        ),
    )


def downgrade():
    op.drop_table("entity_links")
    op.drop_table("versioned_records")
    op.drop_table("games")
