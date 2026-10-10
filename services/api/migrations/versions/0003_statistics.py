"""Immutable licensed statistics, separate from community guides."""

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "statistics_observations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("provider_id", sa.String(300), nullable=False),
        sa.Column("provider_record_id", sa.String(300), nullable=False),
        sa.Column("game_id", sa.String(20), nullable=False),
        sa.Column("ruleset_id", sa.String(300), nullable=False),
        sa.Column("patch", sa.String(300), nullable=False),
        sa.Column("set_id", sa.String(300), nullable=False),
        sa.Column("mode", sa.String(300), nullable=False),
        sa.Column("data_kind", sa.String(20), nullable=False),
        sa.Column("context_kind", sa.String(20), nullable=False),
        sa.Column("context_key", sa.String(64), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("catalog_sha256", sa.String(64), nullable=False),
        sa.Column("imported_at", sa.String(50), nullable=False),
        sa.Column("authorization", sa.JSON(), nullable=False),
        sa.Column("observation", sa.JSON(), nullable=False),
    )
    op.create_index(
        "ix_statistics_scope",
        "statistics_observations",
        ["game_id", "ruleset_id", "patch", "set_id", "mode", "data_kind"],
    )


def downgrade():
    op.drop_table("statistics_observations")
