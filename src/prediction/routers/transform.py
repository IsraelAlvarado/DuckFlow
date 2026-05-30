"""
routers/transform.py — Dataset transformation endpoint.

Endpoints:
  POST /api/v1/transform/{id}

Supported body.operation values:
  groupby         {columns, agg, save_as?}
  scale           {columns, method: minmax|standard|robust, save_as?}
  encode          {column, method: onehot|label, save_as?}
  bin             {column, bins, method: cut|qcut, labels?, save_as?}
  date_features   {column, features:[year|month|day|dayofweek|quarter|week|hour|is_weekend], save_as?}
  log_transform   {columns, base: e|10|2, save_as?}
  rolling         {column, window, agg: mean|sum|std|min|max, save_as?}
  lag             {column, periods, save_as?}
  concat          {dataset_ids, axis: 0|1, save_as?}
  remove_outliers {column, method: iqr|zscore, threshold, save_as?}
  pivot           {index, columns, values, aggfunc: mean|sum|count|min|max, save_as?}
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException

from core.store import dataset_meta, datasets, make_id, register, require_dataset

router = APIRouter()


@router.post("/transform/{dataset_id}")
async def transform_dataset(dataset_id: str, body: dict):
    df = require_dataset(dataset_id).copy()
    log: list[str] = []
    op = body.get("operation", "").strip()

    try:
        # ── GroupBy / Aggregate ───────────────────────────────────────
        if op == "groupby":
            group_cols: list = body.get("columns", [])
            agg_config: dict = body.get("agg", {})
            if not group_cols or not agg_config:
                raise HTTPException(400, "Especifica 'columns' y 'agg'.")
            agg_dict = {c: (f if isinstance(f, list) else [f]) for c, f in agg_config.items()}
            df = df.groupby(group_cols, as_index=False).agg(agg_dict)
            df.columns = [
                "_".join(filter(None, col)) if isinstance(col, tuple) else col
                for col in df.columns
            ]
            log.append(f"GroupBy {group_cols}: {len(df)} grupos resultantes.")

        # ── Scaling ───────────────────────────────────────────────────
        elif op == "scale":
            cols = body.get("columns", [])
            method = body.get("method", "minmax")
            num_cols = df.select_dtypes(include="number").columns.tolist()
            valid = [c for c in cols if c in num_cols]
            if not valid:
                raise HTTPException(400, "Ninguna columna numérica válida.")
            for c in valid:
                s = df[c]
                if method == "minmax":
                    mn, mx = s.min(), s.max()
                    df[c] = (s - mn) / (mx - mn) if mx != mn else 0.0
                elif method == "standard":
                    df[c] = (s - s.mean()) / s.std() if s.std() != 0 else 0.0
                elif method == "robust":
                    q1, q3 = s.quantile(0.25), s.quantile(0.75)
                    iqr = q3 - q1
                    df[c] = (s - s.median()) / iqr if iqr != 0 else 0.0
            log.append(f"Escalado '{method}' aplicado a {valid}.")

        # ── Encoding ──────────────────────────────────────────────────
        elif op == "encode":
            col = body.get("column")
            method = body.get("method", "onehot")
            if not col or col not in df.columns:
                raise HTTPException(400, f"Columna '{col}' no encontrada.")
            if method == "onehot":
                dummies = pd.get_dummies(df[col], prefix=col, dtype=int)
                df = pd.concat([df.drop(columns=[col]), dummies], axis=1)
                log.append(f"One-hot encoding en '{col}': {len(dummies.columns)} nuevas columnas.")
            elif method == "label":
                df[f"{col}_encoded"] = df[col].astype("category").cat.codes
                log.append(f"Label encoding en '{col}' → '{col}_encoded'.")

        # ── Binning ───────────────────────────────────────────────────
        elif op == "bin":
            col = body.get("column")
            n_bins = body.get("bins", 5)
            method = body.get("method", "cut")
            labels = body.get("labels") or None
            if not col or col not in df.columns:
                raise HTTPException(400, f"Columna '{col}' no encontrada.")
            new_col = f"{col}_bin"
            if method == "cut":
                df[new_col] = pd.cut(df[col], bins=n_bins, labels=labels)
            else:
                df[new_col] = pd.qcut(df[col], q=n_bins, labels=labels, duplicates="drop")
            df[new_col] = df[new_col].astype(str)
            log.append(f"Binning ({method}, {n_bins} bins) en '{col}' → '{new_col}'.")

        # ── Date features ─────────────────────────────────────────────
        elif op == "date_features":
            col = body.get("column")
            feats = body.get("features", ["year", "month", "day", "dayofweek"])
            if not col or col not in df.columns:
                raise HTTPException(400, f"Columna '{col}' no encontrada.")
            dt = pd.to_datetime(df[col], errors="coerce")
            week_series = dt.dt.isocalendar().week.astype("Int64").astype("float64")
            feat_map = {
                "year": dt.dt.year, "month": dt.dt.month,
                "day": dt.dt.day, "dayofweek": dt.dt.dayofweek,
                "quarter": dt.dt.quarter, "week": week_series,
                "hour": dt.dt.hour, "is_weekend": (dt.dt.dayofweek >= 5).astype(int),
            }
            added = []
            for f in feats:
                if f in feat_map:
                    df[f"{col}_{f}"] = feat_map[f]
                    added.append(f)
            log.append(f"Features de fecha extraídas de '{col}': {added}.")

        # ── Log transform ─────────────────────────────────────────────
        elif op == "log_transform":
            cols = body.get("columns", [])
            base = body.get("base", "e")
            added = []
            for c in cols:
                if c in df.columns and df[c].dtype in ["float64", "int64", "float32", "int32"]:
                    clipped = df[c].clip(lower=1e-9)
                    suffix = {"10": "_log10", "2": "_log2"}.get(base, "_log")
                    fn = {"10": np.log10, "2": np.log2}.get(base, np.log)
                    df[f"{c}{suffix}"] = fn(clipped)
                    added.append(c)
            log.append(f"Log transform (base {base}) aplicado a {added}.")

        # ── Rolling window ────────────────────────────────────────────
        elif op == "rolling":
            col = body.get("column")
            window = int(body.get("window", 7))
            agg_func = body.get("agg", "mean")
            if not col or col not in df.columns:
                raise HTTPException(400, f"Columna '{col}' no encontrada.")
            new_col = f"{col}_roll{window}_{agg_func}"
            df[new_col] = getattr(df[col].rolling(window=window), agg_func)()
            log.append(f"Rolling {agg_func}({window}) sobre '{col}' → '{new_col}'.")

        # ── Lag feature ───────────────────────────────────────────────
        elif op == "lag":
            col = body.get("column")
            periods = int(body.get("periods", 1))
            if not col or col not in df.columns:
                raise HTTPException(400, f"Columna '{col}' no encontrada.")
            df[f"{col}_lag{periods}"] = df[col].shift(periods)
            log.append(f"Lag {periods} sobre '{col}' → '{col}_lag{periods}'.")

        # ── Concat ────────────────────────────────────────────────────
        elif op == "concat":
            other_ids: list = body.get("dataset_ids", [])
            axis = int(body.get("axis", 0))
            dfs = [df] + [datasets[oid] for oid in other_ids if oid in datasets]
            if len(dfs) < 2:
                raise HTTPException(400, "No se encontraron datasets adicionales.")
            df = pd.concat(dfs, axis=axis, ignore_index=(axis == 0))
            log.append(f"Concatenados {len(dfs)} datasets (axis={axis}): {len(df)} filas.")

        # ── Remove outliers ───────────────────────────────────────────
        elif op == "remove_outliers":
            col = body.get("column")
            method = body.get("method", "iqr")
            threshold = float(body.get("threshold", 1.5))
            if not col or col not in df.columns:
                raise HTTPException(400, f"Columna '{col}' no encontrada.")
            before = len(df)
            if method == "iqr":
                q1, q3 = df[col].quantile(0.25), df[col].quantile(0.75)
                iqr = q3 - q1
                df = df[(df[col] >= q1 - threshold * iqr) & (df[col] <= q3 + threshold * iqr)]
            elif method == "zscore":
                z = np.abs((df[col] - df[col].mean()) / df[col].std())
                df = df[z <= threshold]
            log.append(f"Eliminados {before - len(df)} outliers de '{col}' ({method}, umbral {threshold}).")

        # ── Pivot table ───────────────────────────────────────────────
        elif op == "pivot":
            index = body.get("index")
            columns_col = body.get("columns")
            values = body.get("values")
            aggfunc = body.get("aggfunc", "mean")
            if not all([index, columns_col, values]):
                raise HTTPException(400, "Especifica index, columns y values.")
            pt = pd.pivot_table(
                df, index=index, columns=columns_col,
                values=values, aggfunc=aggfunc, fill_value=0,
            )
            pt.columns = [f"{values}_{c}" for c in pt.columns]
            df = pt.reset_index()
            log.append(f"Pivot table: index='{index}', columns='{columns_col}', values='{values}'.")

        else:
            raise HTTPException(400, f"Operación desconocida: '{op}'.")

        # Save result
        base_name = dataset_meta.get(dataset_id, {}).get("name", "dataset")
        new_name = body.get("save_as") or f"{base_name}_{op}"
        overwrite = bool(body.get("overwrite", False))
        new_id = dataset_id if overwrite else make_id()
        info = register(df, new_name, new_id)

        return {
            "new_dataset_id": new_id,
            "overwritten": overwrite,
            "operations_applied": log,
            "result": info,
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"Error en transformación '{op}': {exc}")