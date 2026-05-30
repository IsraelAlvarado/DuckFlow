"""
routers/datasets.py — Dataset management endpoints.

Endpoints:
  GET    /api/v1/datasets
  DELETE /api/v1/datasets/{id}
  POST   /api/v1/upload-csv
  POST   /api/v1/upload-archive
  POST   /api/v1/extract-from-archive
  GET    /api/v1/export/{id}
"""
from __future__ import annotations

import io
import json
import os
import tempfile
import zipfile
from typing import List

import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from core.store import (
    archives,
    dataset_meta,
    delete_dataset,
    list_meta,
    make_id,
    register,
    require_dataset,
)

# Optional RAR support
try:
    import rarfile
    RAR_SUPPORTED = True
except ImportError:
    RAR_SUPPORTED = False

router = APIRouter()


# ── List ───────────────────────────────────────────────────────────────
@router.get("/datasets")
async def list_datasets():
    """
    Returns all datasets from the DuckDB catalog.
    Metadata is always read from the persistent store so datasets
    survive server restarts.
    """
    return {"datasets": list_meta()}


# ── Delete ─────────────────────────────────────────────────────────────
@router.delete("/datasets/{dataset_id}")
async def remove_dataset(dataset_id: str):
    if dataset_id not in dataset_meta:
        # Try catalog before giving up
        metas = list_meta()
        if not any(m["id"] == dataset_id for m in metas):
            raise HTTPException(404, "Dataset no encontrado.")
    delete_dataset(dataset_id)
    return {"deleted": dataset_id}


# ── Upload CSV(s) ──────────────────────────────────────────────────────
@router.post("/upload-csv")
async def upload_csv(files: List[UploadFile] = File(...)):
    results, errors = [], []
    for file in files:
        if not file.filename.lower().endswith(".csv"):
            errors.append({"name": file.filename, "error": "No es un archivo CSV."})
            continue
        try:
            contents = await file.read()
            df = pd.read_csv(io.BytesIO(contents))
            if df.empty:
                errors.append({"name": file.filename, "error": "El archivo está vacío."})
                continue
            results.append(register(df, file.filename))
        except Exception as exc:
            errors.append({"name": file.filename, "error": str(exc)})
    return {"loaded": results, "errors": errors}


# ── Upload archive (ZIP / RAR) ─────────────────────────────────────────
@router.post("/upload-archive")
async def upload_archive(file: UploadFile = File(...)):
    fname = file.filename.lower()
    is_zip = fname.endswith(".zip")
    is_rar = fname.endswith(".rar")

    if not (is_zip or is_rar):
        raise HTTPException(400, "Solo se aceptan archivos .zip o .rar.")
    if is_rar and not RAR_SUPPORTED:
        raise HTTPException(400, "Soporte RAR no instalado. Ejecuta: pip install rarfile")

    contents = await file.read()
    suffix = ".zip" if is_zip else ".rar"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(contents)
    tmp.close()

    csv_files: List[str] = []
    try:
        if is_zip:
            with zipfile.ZipFile(tmp.name) as z:
                csv_files = [
                    f for f in z.namelist()
                    if f.lower().endswith(".csv") and not os.path.basename(f).startswith(".")
                ]
        else:
            with rarfile.RarFile(tmp.name) as r:
                csv_files = [f for f in r.namelist() if f.lower().endswith(".csv")]
    except Exception as exc:
        os.unlink(tmp.name)
        raise HTTPException(400, f"Error leyendo archivo comprimido: {exc}")

    archive_id = make_id()
    archives[archive_id] = {"path": tmp.name, "type": suffix, "name": file.filename}
    return {"archive_id": archive_id, "files": csv_files, "total": len(csv_files)}


# ── Extract selected CSVs from archive ────────────────────────────────
@router.post("/extract-from-archive")
async def extract_from_archive(
    archive_id: str = Form(...),
    selected_files: str = Form(...),
):
    if archive_id not in archives:
        raise HTTPException(404, "Archivo temporal no encontrado o expirado.")

    arc = archives[archive_id]
    files_to_load: List[str] = json.loads(selected_files)
    results, errors = [], []

    try:
        opener = (
            zipfile.ZipFile(arc["path"])
            if arc["type"] == ".zip"
            else rarfile.RarFile(arc["path"])
        )
        with opener:
            for fname in files_to_load:
                try:
                    with opener.open(fname) as f:
                        df = pd.read_csv(f)
                    results.append(register(df, os.path.basename(fname)))
                except Exception as exc:
                    errors.append({"name": fname, "error": str(exc)})
    except Exception as exc:
        raise HTTPException(500, f"Error extrayendo archivos: {exc}")

    return {"loaded": results, "errors": errors}


# ── Export ─────────────────────────────────────────────────────────────
@router.get("/export/{dataset_id}")
async def export_dataset(dataset_id: str):
    df = require_dataset(dataset_id)
    name = dataset_meta.get(dataset_id, {}).get("name", dataset_id).replace(".csv", "")
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{name}_processed.csv"'},
    )