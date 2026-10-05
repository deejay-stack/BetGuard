"""Private reviewed domain catalog; no synthetic data and no destructive downgrade."""
from alembic import op
import sqlalchemy as sa

revision = "0001_catalog"
down_revision = None
branch_labels = None
depends_on = None
SCHEMA = "betguard_private"


def upgrade():
    op.create_table(
        "domain_catalog",
        sa.Column("hostname", sa.String(253), primary_key=True),
        sa.Column("classification", sa.String(20), nullable=False),
        sa.Column("label_provenance", sa.String(500), nullable=False),
        sa.Column("review_status", sa.String(16), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("classification IN ('gambling', 'non_gambling', 'unknown')", name="classification_values"),
        sa.CheckConstraint("review_status IN ('pending', 'reviewed')", name="review_status_values"),
        sa.CheckConstraint("(review_status = 'reviewed') = (reviewed_at IS NOT NULL)", name="review_date_required"),
        sa.CheckConstraint("length(trim(label_provenance)) > 0", name="provenance_required"),
        sa.CheckConstraint("hostname = lower(hostname) AND length(hostname) BETWEEN 3 AND 253", name="normalized_hostname"),
        sa.CheckConstraint("hostname ~ '^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?([.][a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$' AND hostname !~ '[.][0-9]+$'", name="hostname_syntax"),
        schema=SCHEMA,
    )
    # A NOLOGIN group for the separately provisioned application login.
    # Refuse a colliding role; never trust pre-existing membership/privileges.
    op.execute("CREATE ROLE betguard_reader NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS")
    for target in ["PUBLIC", "anon", "authenticated", "service_role"]:
        if target != "PUBLIC" and not op.get_bind().execute(
            sa.text("SELECT 1 FROM pg_roles WHERE rolname=:role"), {"role": target}
        ).scalar():
            continue
        op.execute(f"REVOKE ALL ON SCHEMA {SCHEMA} FROM {target}")
        op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA {SCHEMA} FROM {target}")
        op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA {SCHEMA} REVOKE ALL ON TABLES FROM {target}")
        op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA {SCHEMA} REVOKE EXECUTE ON FUNCTIONS FROM {target}")
    op.execute(f"ALTER TABLE {SCHEMA}.domain_catalog ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {SCHEMA}.alembic_version ENABLE ROW LEVEL SECURITY")
    op.execute(f"GRANT USAGE ON SCHEMA {SCHEMA} TO betguard_reader")
    op.execute(f"GRANT SELECT ON {SCHEMA}.domain_catalog, {SCHEMA}.alembic_version TO betguard_reader")
    op.execute(f"CREATE POLICY backend_read ON {SCHEMA}.domain_catalog FOR SELECT TO betguard_reader USING (true)")
    op.execute(f"CREATE POLICY backend_version_read ON {SCHEMA}.alembic_version FOR SELECT TO betguard_reader USING (true)")
    op.execute(f"""CREATE FUNCTION {SCHEMA}.set_updated_at() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $$
        BEGIN NEW.updated_at = now(); RETURN NEW; END; $$""")
    op.execute(f"REVOKE ALL ON FUNCTION {SCHEMA}.set_updated_at() FROM PUBLIC")
    op.execute(f"CREATE TRIGGER catalog_updated BEFORE UPDATE ON {SCHEMA}.domain_catalog FOR EACH ROW EXECUTE FUNCTION {SCHEMA}.set_updated_at()")


def downgrade():
    raise RuntimeError("Destructive downgrade disabled. Use a reviewed forward migration to preserve catalog data.")
