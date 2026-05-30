"""
routers/clean.py — Data cleaning endpoint.

Endpoints:
  POST /api/v1/clean/{id}

Accepted body keys:
  drop_duplicates      : bool
  drop_nulls           : "all" | {"columns": [col,...]}
  fill_nulls           : [{column, method: mean|median|mode|ffill|bfill|value, value?}]
  drop_columns         : [col,...]
  rename_columns       : {old: new,...}
  filter_rows          : {column, operator: ==|!=|>|<|>=|<=|contains, value}
  convert_dtype        : [{column, dtype: numeric|datetime|string|category}]
  save_as              : str
  overwrite            : bool
"""
from __future__ import annotations

from typing import Any, List

from fastapi import APIRouter, HTTPException

from core.store import dataset_meta, make_id, register, require_dataset

router = APIRouter()


@router.post("/clean/{dataset_id}")
async def clean_dataset(dataset_id: str, body: dict):
    df = require_dataset(dataset_id).copy()
    log: List[str] = []

    try:
        # Drop duplicates
        if body.get("drop_duplicates"):
            before = len(df)
            df = df.drop_duplicates()
            log.append(f"Eliminados {before - len(df)} duplicados.")

        # Drop nulls
        if dn := body.get("drop_nulls"):
            before = len(df)
            if dn == "all" or (isinstance(dn, dict) and dn.get("columns") == "all"):
                df = df.dropna()
            elif isinstance(dn, dict) and dn.get("columns"):
                df = df.dropna(subset=dn["columns"])
            log.append(f"Eliminadas {before - len(df)} filas con valores nulos.")

        # Fill nulls
        fills = body.get("fill_nulls", [])
        if isinstance(fills, dict):
            fills = [fills]
        for fill in fills:
            col = fill.get("column")
            method = fill.get("method", "value")
            if col and col in df.columns:
                if method == "mean":
                    df[col] = df[col].fillna(df[col].mean())
                elif method == "median":
                    df[col] = df[col].fillna(df[col].median())
                elif method == "mode":
                    df[col] = df[col].fillna(df[col].mode().iloc[0])
                elif method == "ffill":
                    df[col] = df[col].ffill()
                elif method == "bfill":
                    df[col] = df[col].bfill()
                else:
                    df[col] = df[col].fillna(fill.get("value", ""))
                log.append(f"Nulos en '{col}' rellenados con método '{method}'.")

        # Drop columns
        if cols := body.get("drop_columns"):
            df = df.drop(columns=[c for c in cols if c in df.columns], errors="ignore")
            log.append(f"Columnas eliminadas: {cols}")

        # Rename columns
        if renames := body.get("rename_columns"):
            df = df.rename(columns=renames)
            log.append(f"Columnas renombradas: {renames}")

        # Filter rows
        if fc := body.get("filter_rows"):
            col, op, val = fc.get("column"), fc.get("operator"), fc.get("value")
            if col and col in df.columns:
                before = len(df)
                ops_map = {
                    "==": lambda s, v: s == v,
                    "!=": lambda s, v: s != v,
                    ">":  lambda s, v: s > v,
                    "<":  lambda s, v: s < v,
                    ">=": lambda s, v: s >= v,
                    "<=": lambda s, v: s <= v,
                    "contains": lambda s, v: s.astype(str).str.contains(str(v), na=False),
                }
                if op in ops_map:
                    df = df[ops_map[op](df[col], val)]
                log.append(f"Filtro '{col} {op} {val}': {before - len(df)} filas eliminadas.")

        # Convert dtypes
        convs = body.get("convert_dtype", [])
        if isinstance(convs, dict):
            convs = [convs]
        for conv in convs:
            col, dtype = conv.get("column"), conv.get("dtype")
            if col and col in df.columns:
                import pandas as pd
                if dtype == "numeric":
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                elif dtype == "datetime":
                    df[col] = pd.to_datetime(df[col], errors="coerce")
                elif dtype == "string":
                    df[col] = df[col].astype(str)
                elif dtype == "category":
                    df[col] = df[col].astype("category")
                log.append(f"'{col}' convertido a {dtype}.")

        base_name = dataset_meta.get(dataset_id, {}).get("name", "dataset")
        new_name = body.get("save_as") or f"{base_name}_limpio"
        new_id = dataset_id if body.get("overwrite") else make_id()
        info = register(df, new_name, new_id)

        return {
            "new_dataset_id": new_id,
            "overwritten": bool(body.get("overwrite")),
            "operations_applied": log,
            "result": info,
        }

    except Exception as exc:
        raise HTTPException(500, f"Error durante la limpieza: {exc}")