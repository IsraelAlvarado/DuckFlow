"""
routers/eda.py — Exploratory Data Analysis endpoint.

Endpoints:
  GET /api/v1/eda/{id}
"""
from __future__ import annotations

from typing import Any, Dict

import numpy as np
from fastapi import APIRouter

from core.store import dataset_meta, require_dataset

router = APIRouter()


@router.get("/eda/{dataset_id}")
async def exploratory_analysis(dataset_id: str):
    df = require_dataset(dataset_id)
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    categorical_cols = df.select_dtypes(include=["object", "category"]).columns.tolist()

    # Missing values
    missing_counts = df.isnull().sum()
    missing_data = [
        {
            "column": col,
            "missing": int(missing_counts[col]),
            "pct": round(float(missing_counts[col] / len(df) * 100), 2),
        }
        for col in df.columns
        if missing_counts[col] > 0
    ]

    # Numeric stats
    numeric_stats = []
    for col in numeric_cols:
        s = df[col].dropna()
        if len(s) == 0:
            continue
        numeric_stats.append({
            "column": col,
            "count": len(s),
            "nulls": int(df[col].isnull().sum()),
            "mean": round(float(s.mean()), 4),
            "median": round(float(s.median()), 4),
            "std": round(float(s.std()), 4),
            "min": round(float(s.min()), 4),
            "max": round(float(s.max()), 4),
            "q25": round(float(s.quantile(0.25)), 4),
            "q75": round(float(s.quantile(0.75)), 4),
            "skewness": round(float(s.skew()), 4),
            "kurtosis": round(float(s.kurtosis()), 4),
        })

    # Categorical stats
    categorical_stats = []
    for col in categorical_cols:
        vc = df[col].value_counts()
        categorical_stats.append({
            "column": col,
            "unique": int(df[col].nunique()),
            "nulls": int(df[col].isnull().sum()),
            "top_value": str(vc.index[0]) if len(vc) > 0 else "",
            "top_count": int(vc.iloc[0]) if len(vc) > 0 else 0,
            "top_10": [{"name": str(k), "value": int(v)} for k, v in vc.head(10).items()],
        })

    # Correlation matrix
    correlation: Dict[str, Any] = {}
    if len(numeric_cols) > 1:
        corr_df = df[numeric_cols].corr().round(3)
        correlation = {
            "columns": numeric_cols,
            "matrix": corr_df.values.tolist(),
        }

    # Histograms (max 8 columns)
    distributions: Dict[str, Any] = {}
    for col in numeric_cols[:8]:
        clean = df[col].dropna()
        if len(clean) == 0:
            continue
        counts, edges = np.histogram(clean, bins=20)
        distributions[col] = {
            "counts": counts.tolist(),
            "bins": [round(float(x), 4) for x in edges.tolist()],
        }

    sample = df.head(15).fillna("").astype(str).to_dict(orient="records")

    return {
        "dataset_id": dataset_id,
        "name": dataset_meta[dataset_id]["name"],
        "shape": {"rows": len(df), "cols": len(df.columns)},
        "columns": df.columns.tolist(),
        "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
        "missing_data": missing_data,
        "numeric_stats": numeric_stats,
        "categorical_stats": categorical_stats,
        "correlation": correlation,
        "distributions": distributions,
        "duplicates": int(df.duplicated().sum()),
        "sample_data": sample,
    }