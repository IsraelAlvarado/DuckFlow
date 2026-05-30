"""
main.py — Application entry point.
"""
from __future__ import annotations

import io
import sys
from contextlib import asynccontextmanager
from pathlib import Path

_PKG_DIR = Path(__file__).resolve().parent
if str(_PKG_DIR) not in sys.path:
    sys.path.insert(0, str(_PKG_DIR))

import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from core.store import load_all
from routers import (
    clean,
    datasets,
    eda,
    export_analysis,
    kaggle,
    merge,
    stats,
    storage,
    train,
    transform,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_all()
    yield


app = FastAPI(
    title="Universal Data Analyzer API",
    version="2.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PREFIX = "/api/v1"

app.include_router(datasets.router,        prefix=PREFIX)
app.include_router(eda.router,             prefix=PREFIX)
app.include_router(clean.router,           prefix=PREFIX)
app.include_router(merge.router,           prefix=PREFIX)
app.include_router(transform.router,       prefix=PREFIX)
app.include_router(storage.router,         prefix=PREFIX)
app.include_router(stats.router,           prefix=PREFIX)
app.include_router(kaggle.router,          prefix=PREFIX)
app.include_router(export_analysis.router, prefix=PREFIX)
app.include_router(train.router,           prefix=PREFIX)  # train al final por /train/models


@app.post("/api/v1/analyze")
async def analyze_legacy(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "El archivo debe ser CSV.")
    contents = await file.read()
    df = pd.read_csv(io.BytesIO(contents))
    if df.empty:
        raise HTTPException(400, "El conjunto de datos esta vacio.")

    numeric_cols     = df.select_dtypes(include="number").columns.tolist()
    categorical_cols = df.select_dtypes(include=["object", "category"]).columns.tolist()
    chart_data = []
    if categorical_cols and numeric_cols:
        cat, num = categorical_cols[0], numeric_cols[0]
        top = df.groupby(cat)[num].sum().nlargest(5)
        chart_data = [{"name": str(k), "value": float(v)} for k, v in top.items()]

    return {
        "filename":                  file.filename,
        "total_rows":                len(df),
        "total_features":            len(df.columns),
        "numeric_columns_count":     len(numeric_cols),
        "categorical_columns_count": len(categorical_cols),
        "target_metric_name":        numeric_cols[0]     if numeric_cols     else "N/A",
        "target_category_name":      categorical_cols[0] if categorical_cols else "N/A",
        "chart_data":                chart_data,
    }