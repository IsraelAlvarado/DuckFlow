"""
core/store.py — Dataset store backed by DuckDB + Parquet.

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

import duckdb
import pandas as pd
from fastapi import HTTPException

# ── Storage paths ──────────────────────────────────────────────────────
DATA_DIR = Path(os.getenv("DATA_DIR", "data/datasets"))
DB_PATH  = Path(os.getenv("DB_PATH",  "data/catalog.duckdb"))

DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# ── Lazy singleton connection ──────────────────────────────────────────
_con: Optional[duckdb.DuckDBPyConnection] = None


def _get_con() -> duckdb.DuckDBPyConnection:
    global _con
    if _con is None:
        _con = duckdb.connect(str(DB_PATH))
        _con.execute("""
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
    return _con


# ── In-memory caches ───────────────────────────────────────────────────
datasets:     Dict[str, pd.DataFrame] = {}
dataset_meta: Dict[str, dict]         = {}
archives:     Dict[str, dict]         = {}


# ── Internal helpers ───────────────────────────────────────────────────

def _row_to_meta(row) -> dict:
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


def _parquet_path(dataset_id: str) -> Path:
    return DATA_DIR / f"{dataset_id}.parquet"


# ── Public API ─────────────────────────────────────────────────────────

def make_id() -> str:
    return str(uuid.uuid4())[:8]


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

    _get_con().execute("""
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

    rows = _get_con().execute(
        "SELECT parquet_path FROM datasets WHERE id = ?", [dataset_id]
    ).fetchall()
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
    _get_con().execute("DELETE FROM datasets WHERE id = ?", [dataset_id])
    ppath = _parquet_path(dataset_id)
    if ppath.exists():
        ppath.unlink()
    datasets.pop(dataset_id, None)
    dataset_meta.pop(dataset_id, None)


def list_meta() -> list:
    rows = _get_con().execute(
        "SELECT * FROM datasets ORDER BY created_at ASC"
    ).fetchall()
    result = []
    for row in rows:
        m = _row_to_meta(row)
        dataset_meta[m["id"]] = m
        result.append(m)
    return result


def load_all() -> None:
    for m in list_meta():
        dataset_meta[m["id"]] = m
    print(f"[store] Catalog loaded: {len(dataset_meta)} dataset(s) found.")