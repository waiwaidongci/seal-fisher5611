Schema v1 is defined by the SQLAlchemy models and created at startup via Base.metadata.create_all. For this local small application no destructive migration is run. Back up named db-data before modifying schemas.

Schema v2 (additive) adds `studies.kind` and `runs.kind` (VARCHAR(40), NOT NULL, DEFAULT 'seal_fisher'). Existing rows therefore keep the legacy Fisher study semantics. `src/config/schema.py` adds these columns with `ALTER TABLE ... ADD COLUMN` when an old volume is started; no table or row is dropped or rewritten.
