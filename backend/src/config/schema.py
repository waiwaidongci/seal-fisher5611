import os
from sqlalchemy import inspect,text
from src.config.database import engine

# Schema v1 is created by SQLAlchemy.  These additive upgrades let an
# existing MySQL volume gain the new columns without a destructive migration.
UPGRADES=[
    ('studies','kind',"VARCHAR(40) NOT NULL DEFAULT 'seal_fisher'"),
    ('runs','kind',"VARCHAR(40) NOT NULL DEFAULT 'seal_fisher'"),
]

def ensure_schema():
    inspector=inspect(engine)
    tables=set(inspector.get_table_names())
    with engine.begin() as conn:
        for table,column,ddl in UPGRADES:
            if table not in tables: continue
            columns={c['name'] for c in inspector.get_columns(table)}
            if column not in columns:
                conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {column} {ddl}'))
