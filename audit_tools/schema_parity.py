"""Compare live migrated schema against Base.metadata (ORM source of truth)."""
import os
os.environ.setdefault("SECRET_KEY", "x")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://hadiflow:hadiflow123@localhost:5432/hadiflow_test")
import sqlalchemy as sa
from sqlalchemy import create_engine, inspect
import app.models  # registers all models
from app.database.base import Base

engine = create_engine(os.environ["DATABASE_URL"])
insp = inspect(engine)
live_tables = set(insp.get_table_names()) - {"alembic_version"}
meta_tables = set(Base.metadata.tables.keys())
problems = []
if live_tables - meta_tables:
    problems.append(f"EXTRA tables in DB not in models: {sorted(live_tables - meta_tables)}")
if meta_tables - live_tables:
    problems.append(f"MISSING tables in DB: {sorted(meta_tables - live_tables)}")

def norm_type(t):
    s = str(t).upper()
    return s.replace("TIMESTAMP WITHOUT TIME ZONE", "TIMESTAMP").replace("DATETIME", "TIMESTAMP")

for t in sorted(meta_tables & live_tables):
    model = {c.name: c for c in Base.metadata.tables[t].columns}
    live = {c["name"]: c for c in insp.get_columns(t)}
    for name in set(model) - set(live):
        problems.append(f"{t}: column '{name}' in model but MISSING in DB")
    for name in set(live) - set(model):
        problems.append(f"{t}: column '{name}' in DB but not in model")
    for name in set(model) & set(live):
        m, l = model[name], live[name]
        if bool(m.nullable) != bool(l["nullable"]):
            problems.append(f"{t}.{name}: nullable mismatch model={m.nullable} db={l['nullable']}")
        mt, lt = norm_type(m.type), norm_type(l["type"])
        # treat VARCHAR without length == VARCHAR(n) mismatch as real
        if mt != lt and not (mt.startswith("VARCHAR") and lt.startswith("VARCHAR") and mt == "VARCHAR"):
            problems.append(f"{t}.{name}: type mismatch model={mt} db={lt}")
    # unique constraints on users.mobile etc
    model_unique = {c.name for c in Base.metadata.tables[t].columns if c.unique}
    live_unique_cols = set()
    for uc in insp.get_unique_constraints(t):
        if len(uc["column_names"]) == 1:
            live_unique_cols.add(uc["column_names"][0])
    for ix in insp.get_indexes(t):
        if ix.get("unique") and len(ix["column_names"]) == 1:
            live_unique_cols.add(ix["column_names"][0])
    for name in model_unique - live_unique_cols:
        problems.append(f"{t}.{name}: model says UNIQUE but DB has no unique constraint/index")

if problems:
    print("SCHEMA MISMATCHES:")
    for p in problems:
        print(" -", p)
else:
    print("SCHEMA PARITY OK: migrated DB matches ORM metadata")
