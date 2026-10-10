"""Separate community imports and audited corrections from statistics."""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "community_imports",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
    )
    op.create_table(
        "community_rows",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column("import_id", sa.String(64), sa.ForeignKey("community_imports.id"), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("raw", sa.JSON(), nullable=False),
        sa.Column("current", sa.JSON(), nullable=False),
        sa.Column("history", sa.JSON(), nullable=False),
    )
    op.create_index("ix_community_rows_import_id", "community_rows", ["import_id"])


def downgrade():
    op.drop_table("community_rows")
    op.drop_table("community_imports")
