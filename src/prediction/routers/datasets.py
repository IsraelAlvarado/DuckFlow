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

from core.engine import DEFAULT_ENGINE, SUPPORTED_ENGINES, read_csv
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
        metas = list_meta()
        if not any(m["id"] == dataset_id for m in metas):
            raise HTTPException(404, "Dataset no encontrado.")
    delete_dataset(dataset_id)
    return {"deleted": dataset_id}


# ── Upload CSV(s) ──────────────────────────────────────────────────────
@router.post("/upload-csv")
async def upload_csv(
    files: List[UploadFile] = File(...),
    engine: str = Form(DEFAULT_ENGINE),
):
    """
    Upload one or more CSV files.

    Parameters
    ----------
    files  : one or more CSV files
    engine : parsing engine — "pandas" (default) or "polars"
    """
    if engine not in SUPPORTED_ENGINES:
        raise HTTPException(
            400,
            f"Engine '{engine}' no soportado. Usa: {', '.join(SUPPORTED_ENGINES)}",
        )

    results, errors = [], []
    for file in files:
        if not file.filename.lower().endswith(".csv"):
            errors.append({"name": file.filename, "error": "No es un archivo CSV."})
            continue
        try:
            contents = await file.read()
            df = read_csv(contents, engine=engine)
            if df.empty:
                errors.append({"name": file.filename, "error": "El archivo está vacío."})
                continue
            info = register(df, file.filename)
            info["engine_used"] = engine
            results.append(info)
        except Exception as exc:
            errors.append({"name": file.filename, "error": str(exc)})

    return {"loaded": results, "errors": errors, "engine": engine}


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
    engine: str = Form(DEFAULT_ENGINE),
):
    """
    Extract and load specific CSV files from a previously uploaded archive.

    Parameters
    ----------
    archive_id     : ID returned by /upload-archive
    selected_files : JSON array of file paths within the archive
    engine         : parsing engine — "pandas" (default) or "polars"
    """
    if engine not in SUPPORTED_ENGINES:
        raise HTTPException(
            400,
            f"Engine '{engine}' no soportado. Usa: {', '.join(SUPPORTED_ENGINES)}",
        )

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
                        raw = f.read()
                    df = read_csv(raw, engine=engine)
                    info = register(df, os.path.basename(fname))
                    info["engine_used"] = engine
                    results.append(info)
                except Exception as exc:
                    errors.append({"name": fname, "error": str(exc)})
    except Exception as exc:
        raise HTTPException(500, f"Error extrayendo archivos: {exc}")

    return {"loaded": results, "errors": errors, "engine": engine}


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