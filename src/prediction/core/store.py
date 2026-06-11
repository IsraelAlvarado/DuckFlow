"""
core/store.py — Dataset store backed by DuckDB (local) or Supabase PostgreSQL.

Public API:
  register(df, name, dataset_id=None) -> dict
  require_dataset(dataset_id)         -> pd.DataFrame
  make_id()                           -> str
  list_meta()                         -> list[dict]
  delete_dataset(dataset_id)
  load_all()                          (called once at startup)
"""
from __future__ import annotations

import json as _json
import os
import uuid
from pathlib import Path
from typing import Dict, Optional

import pandas as pd
from fastapi import HTTPException

DATA_DIR = Path(os.getenv("DATA_DIR", "data/datasets"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL", "")

USE_SUPABASE = bool(DATABASE_URL)

datasets:     Dict[str, pd.DataFrame] = {}
dataset_meta: Dict[str, dict]         = {}
archives:     Dict[str, dict]         = {}

def _parquet_path(dataset_id: str) -> Path:
    return DATA_DIR / f"{dataset_id}.parquet"

def make_id() -> str:
    return str(uuid.uuid4())[:8]

# ── DuckDB backend ─────────────────────────────────────────────────────

_con_duckdb: Optional["duckdb.DuckDBPyConnection"] = None

def _init_duckdb():
    global _con_duckdb
    import duckdb
    db_path = os.getenv("DB_PATH", "data/catalog.duckdb")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    _con_duckdb = duckdb.connect(db_path)
    _con_duckdb.execute("""
        CREATE TABLE IF NOT EXISTS datasets (
            id                       VARCHAR PRIMARY KEY,
            name                     VARCHAR NOT NULL,
            parquet_path             VARCHAR NOT NULL,
            total_rows               BIGINT,
            total_features           INTEGER,
            columns_json             VARCHAR,
            numeric_columns_json     VARCHAR,
            categorical_columns_json VARCHAR,
            datetime_columns_json    VARCHAR,
            missing_total            BIGINT,
            duplicates               BIGINT,
            memory_kb                DOUBLE,
            created_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

def _get_con_duckdb():
    global _con_duckdb
    if _con_duckdb is None:
        _init_duckdb()
    return _con_duckdb

def _row_to_meta_duckdb(row) -> dict:
    (id_, name, ppath, rows, feats, cols, num_cols, cat_cols,
     dt_cols, missing, dupes, mem_kb, created_at) = row
    return {
        "id":                        id_,
        "name":                      name,
        "total_rows":                rows,
        "total_features":            feats,
        "columns":                   _json.loads(cols     or "[]"),
        "numeric_columns":           _json.loads(num_cols or "[]"),
        "categorical_columns":       _json.loads(cat_cols or "[]"),
        "datetime_columns":          _json.loads(dt_cols  or "[]"),
        "numeric_columns_count":     len(_json.loads(num_cols or "[]")),
        "categorical_columns_count": len(_json.loads(cat_cols or "[]")),
        "missing_total":             missing,
        "duplicates":                dupes,
        "memory_kb":                 mem_kb,
        "created_at":                str(created_at),
    }

# ── Supabase / PostgreSQL backend ──────────────────────────────────────

_con_pg = None

def _get_con_pg():
    global _con_pg
    if _con_pg is not None:
        return _con_pg
    import psycopg2
    _con_pg = psycopg2.connect(DATABASE_URL)
    _con_pg.autocommit = True
    with _con_pg.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS datasets (
                id                       TEXT PRIMARY KEY,
                name                     TEXT NOT NULL,
                parquet_path             TEXT NOT NULL,
                total_rows               BIGINT,
                total_features           INTEGER,
                columns_json             TEXT,
                numeric_columns_json     TEXT,
                categorical_columns_json TEXT,
                datetime_columns_json    TEXT,
                missing_total            BIGINT,
                duplicates               BIGINT,
                memory_kb                DOUBLE PRECISION,
                created_at               TIMESTAMP DEFAULT NOW()
            )
        """)
    return _con_pg

def _row_to_meta_pg(row) -> dict:
    (id_, name, ppath, rows, feats, cols, num_cols, cat_cols,
     dt_cols, missing, dupes, mem_kb, created_at) = row
    return {
        "id":                        id_,
        "name":                      name,
        "total_rows":                rows,
        "total_features":            feats,
        "columns":                   _json.loads(cols     or "[]"),
        "numeric_columns":           _json.loads(num_cols or "[]"),
        "categorical_columns":       _json.loads(cat_cols or "[]"),
        "datetime_columns":          _json.loads(dt_cols  or "[]"),
        "numeric_columns_count":     len(_json.loads(num_cols or "[]")),
        "categorical_columns_count": len(_json.loads(cat_cols or "[]")),
        "missing_total":             missing,
        "duplicates":                dupes,
        "memory_kb":                 mem_kb,
        "created_at":                str(created_at),
    }

# ── Unified helpers ────────────────────────────────────────────────────

def _get_con():
    if USE_SUPABASE:
        return _get_con_pg()
    return _get_con_duckdb()

def _execute(sql: str, params: Optional[list] = None):
    con = _get_con()
    if USE_SUPABASE:
        with con.cursor() as cur:
            cur.execute(sql, params or [])
            if sql.strip().upper().startswith("SELECT"):
                return cur.fetchall()
            return None
    else:
        return con.execute(sql, params or [])

def _fetchall(sql: str, params: Optional[list] = None) -> list:
    con = _get_con()
    if USE_SUPABASE:
        with con.cursor() as cur:
            cur.execute(sql, params or [])
            return cur.fetchall()
    else:
        return con.execute(sql, params or []).fetchall()

# ── Public API ─────────────────────────────────────────────────────────

def register(df: pd.DataFrame, name: str,
             dataset_id: Optional[str] = None) -> dict:
    did = dataset_id or make_id()

    numeric_cols     = df.select_dtypes(include="number").columns.tolist()
    categorical_cols = df.select_dtypes(include=["object", "category"]).columns.tolist()
    datetime_cols    = df.select_dtypes(include="datetime").columns.tolist()

    ppath = _parquet_path(did)
    df.to_parquet(ppath, index=False, engine="pyarrow")

    info = {
        "id":                        did,
        "name":                      name,
        "total_rows":                len(df),
        "total_features":            len(df.columns),
        "columns":                   df.columns.tolist(),
        "numeric_columns":           numeric_cols,
        "categorical_columns":       categorical_cols,
        "datetime_columns":          datetime_cols,
        "numeric_columns_count":     len(numeric_cols),
        "categorical_columns_count": len(categorical_cols),
        "missing_total":             int(df.isnull().sum().sum()),
        "duplicates":                int(df.duplicated().sum()),
        "memory_kb":                 round(df.memory_usage(deep=True).sum() / 1024, 2),
    }

    if USE_SUPABASE:
        _execute("""
            INSERT INTO datasets
              (id, name, parquet_path, total_rows, total_features,
               columns_json, numeric_columns_json, categorical_columns_json,
               datetime_columns_json, missing_total, duplicates, memory_kb)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
              name = EXCLUDED.name,
              parquet_path = EXCLUDED.parquet_path,
              total_rows = EXCLUDED.total_rows,
              total_features = EXCLUDED.total_features,
              columns_json = EXCLUDED.columns_json,
              numeric_columns_json = EXCLUDED.numeric_columns_json,
              categorical_columns_json = EXCLUDED.categorical_columns_json,
              datetime_columns_json = EXCLUDED.datetime_columns_json,
              missing_total = EXCLUDED.missing_total,
              duplicates = EXCLUDED.duplicates,
              memory_kb = EXCLUDED.memory_kb
        """, [
            did, name, str(ppath),
            info["total_rows"], info["total_features"],
            _json.dumps(info["columns"]),
            _json.dumps(numeric_cols),
            _json.dumps(categorical_cols),
            _json.dumps(datetime_cols),
            info["missing_total"],
            info["duplicates"],
            info["memory_kb"],
        ])
    else:
        _execute("""
            INSERT OR REPLACE INTO datasets
              (id, name, parquet_path, total_rows, total_features,
               columns_json, numeric_columns_json, categorical_columns_json,
               datetime_columns_json, missing_total, duplicates, memory_kb)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            did, name, str(ppath),
            info["total_rows"], info["total_features"],
            _json.dumps(info["columns"]),
            _json.dumps(numeric_cols),
            _json.dumps(categorical_cols),
            _json.dumps(datetime_cols),
            info["missing_total"],
            info["duplicates"],
            info["memory_kb"],
        ])

    datasets[did]     = df
    dataset_meta[did] = info
    return info


def require_dataset(dataset_id: str) -> pd.DataFrame:
    if dataset_id in datasets:
        return datasets[dataset_id]

    rows = _fetchall(
        "SELECT parquet_path FROM datasets WHERE id = %s" if USE_SUPABASE
        else "SELECT parquet_path FROM datasets WHERE id = ?",
        [dataset_id]
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Dataset no encontrado.")
    ppath = Path(rows[0][0])
    if not ppath.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Archivo Parquet no encontrado: {ppath.name}.")

    df = pd.read_parquet(ppath, engine="pyarrow")
    datasets[dataset_id] = df
    return df


def delete_dataset(dataset_id: str) -> None:
    if USE_SUPABASE:
        _execute("DELETE FROM datasets WHERE id = %s", [dataset_id])
    else:
        _execute("DELETE FROM datasets WHERE id = ?", [dataset_id])
    ppath = _parquet_path(dataset_id)
    if ppath.exists():
        ppath.unlink()
    datasets.pop(dataset_id, None)
    dataset_meta.pop(dataset_id, None)


def list_meta() -> list:
    rows = _fetchall(
        "SELECT * FROM datasets ORDER BY created_at ASC"
    )
    result = []
    for row in rows:
        if USE_SUPABASE:
            m = _row_to_meta_pg(row)
        else:
            m = _row_to_meta_duckdb(row)
        dataset_meta[m["id"]] = m
        result.append(m)
    return result


def load_all() -> None:
    for m in list_meta():
        dataset_meta[m["id"]] = m
    backend = "Supabase PostgreSQL" if USE_SUPABASE else "DuckDB"
    print(f"[store] Catalog loaded ({backend}): {len(dataset_meta)} dataset(s) found.")
