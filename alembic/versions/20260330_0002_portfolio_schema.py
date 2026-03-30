"""Portfolio holdings and transactions tables."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260330_0002"
down_revision = "20260311_0001"
branch_labels = None
depends_on = None

UTC_NOW = sa.text("TIMEZONE('utc', NOW())")


def upgrade() -> None:
    op.create_table(
        "portfolio_holdings",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_wa_id", sa.String(64), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("company_name", sa.String(255), nullable=True),
        sa.Column("quantity", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("avg_price", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=UTC_NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=UTC_NOW),
        sa.UniqueConstraint("user_wa_id", "symbol", name="uq_portfolio_user_symbol"),
    )
    op.create_index("ix_portfolio_holdings_user_wa_id", "portfolio_holdings", ["user_wa_id"])

    op.create_table(
        "portfolio_transactions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "holding_id",
            sa.BigInteger(),
            sa.ForeignKey("portfolio_holdings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_wa_id", sa.String(64), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("price_per_share", sa.Float(), nullable=False),
        sa.Column("total_value", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=UTC_NOW),
    )
    op.create_index("ix_portfolio_transactions_user_wa_id", "portfolio_transactions", ["user_wa_id"])


def downgrade() -> None:
    op.drop_index("ix_portfolio_transactions_user_wa_id", table_name="portfolio_transactions")
    op.drop_table("portfolio_transactions")
    op.drop_index("ix_portfolio_holdings_user_wa_id", table_name="portfolio_holdings")
    op.drop_table("portfolio_holdings")
