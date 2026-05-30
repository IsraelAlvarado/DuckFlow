"""
routers/storage.py — Cloud storage sync endpoints.
FIXED: todas las importaciones de core.store son lazy (dentro de funciones)
para evitar circular imports durante la inicialización del módulo.
"""
from __future__ import annotations

import io
import json as _json
import os

from fastapi import APIRouter, HTTPException

router = APIRouter()

ALL_FORMATS = ["parquet", "csv", "py", "ipynb"]

# ── Backend factory ────────────────────────────────────────────────────

def _get_backend():
    backend_type = os.getenv("STORAGE_BACKEND", "").lower()
    if backend_type == "gdrive":
        folder_id = os.getenv("GDRIVE_FOLDER_ID", "")
        if not folder_id:
            raise HTTPException(503, "Configura GDRIVE_FOLDER_ID en .env para usar Google Drive.")
        from core.storage_backends import GoogleDriveBackend
        return GoogleDriveBackend(folder_id=folder_id)
    elif backend_type == "s3":
        bucket = os.getenv("S3_BUCKET", "")
        if not bucket:
            raise HTTPException(503, "Configura S3_BUCKET en .env para usar S3 / MinIO / R2.")
        from core.storage_backends import S3Backend
        return S3Backend(
            bucket=bucket,
            prefix=os.getenv("S3_PREFIX", "datasets/"),
            endpoint=os.getenv("S3_ENDPOINT") or None,
        )
    else:
        raise HTTPException(
            503,
            "No hay backend de nube configurado. "
            "Agrega STORAGE_BACKEND=gdrive|s3 en tu archivo .env."
        )


# ── Helpers ────────────────────────────────────────────────────────────

def _build_csv_bytes(df) -> bytes:
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()


def _build_parquet_bytes(df) -> bytes:
    buf = io.BytesIO()
    df.to_parquet(buf, index=False, engine="pyarrow")
    return buf.getvalue()


def _build_analysis_bytes(dataset_id: str, fmt: str, sections: list) -> bytes:
    from core.store import require_dataset, dataset_meta as dm
    from routers.export_analysis import _build_py_script, _build_ipynb, ALL_SECTIONS
    df   = require_dataset(dataset_id)
    name = dm.get(dataset_id, {}).get("name", dataset_id)
    valid = [s for s in ALL_SECTIONS if s in sections] or list(ALL_SECTIONS)
    if fmt == "py":
        return _build_py_script(df, name, valid).encode("utf-8")
    nb = _build_ipynb(df, name, valid)
    return _json.dumps(nb, ensure_ascii=False, indent=1).encode("utf-8")


MIME_MAP = {"parquet": "application/octet-stream", "csv": "text/csv",
            "py": "text/x-python", "ipynb": "application/x-ipynb+json"}
EXT_MAP  = {"parquet": ".parquet", "csv": ".csv", "py": ".py", "ipynb": ".ipynb"}


def _push_bytes_gdrive(backend, folder_id, filename, data, mime):
    from googleapiclient.http import MediaIoBaseUpload
    buf = io.BytesIO(data)
    existing = backend._find_file(filename)
    if existing:
        backend._svc.files().update(
            fileId=existing,
            media_body=MediaIoBaseUpload(buf, mimetype=mime),
            supportsAllDrives=True,
        ).execute()
        return existing
    file_meta = {"name": filename, "parents": [folder_id]}
    r = backend._svc.files().create(
        body=file_meta,
        media_body=MediaIoBaseUpload(buf, mimetype=mime),
        fields="id", supportsAllDrives=True,
    ).execute()
    return r["id"]


def _push_bytes_s3(backend, key_prefix, filename, data, content_type):
    key = f"{key_prefix}{filename}"
    backend._s3.put_object(Bucket=backend.bucket, Key=key,
                           Body=data, ContentType=content_type)
    return key


def _push_format(backend, dataset_id, fmt, sections, safe_name):
    from core.store import require_dataset
    filename = f"{safe_name}{EXT_MAP[fmt]}"
    try:
        df = require_dataset(dataset_id)
        if fmt == "parquet":
            data = _build_parquet_bytes(df)
        elif fmt == "csv":
            data = _build_csv_bytes(df)
        elif fmt in ("py", "ipynb"):
            data = _build_analysis_bytes(dataset_id, fmt, sections)
        else:
            return {"format": fmt, "uri": None, "error": f"Formato desconocido: {fmt}"}
        bt = os.getenv("STORAGE_BACKEND", "").lower()
        if bt == "gdrive":
            uri = _push_bytes_gdrive(backend, os.getenv("GDRIVE_FOLDER_ID", ""),
                                     filename, data, MIME_MAP[fmt])
        elif bt == "s3":
            uri = _push_bytes_s3(backend, backend.prefix, filename, data, MIME_MAP[fmt])
        else:
            return {"format": fmt, "uri": None, "error": "Backend no configurado"}
        return {"format": fmt, "filename": filename, "uri": uri}
    except Exception as exc:
        return {"format": fmt, "uri": None, "error": str(exc)}


# ── Endpoints ──────────────────────────────────────────────────────────

@router.get("/storage/status")
async def storage_status():
    from core.store import dataset_meta
    bt = os.getenv("STORAGE_BACKEND", "none").lower()
    d  = {"backend": bt, "configured": bt in ("gdrive", "s3")}
    if bt == "gdrive": d["folder_id"] = os.getenv("GDRIVE_FOLDER_ID", "—")
    elif bt == "s3":
        d["bucket"]   = os.getenv("S3_BUCKET", "—")
        d["prefix"]   = os.getenv("S3_PREFIX", "datasets/")
        d["endpoint"] = os.getenv("S3_ENDPOINT", "AWS S3")
    d["local_datasets"]    = len(dataset_meta)
    d["available_formats"] = ALL_FORMATS
    return d


@router.post("/storage/push")
async def push_all():
    from core.store import datasets, dataset_meta
    from core.storage_backends import sync_push_all
    return sync_push_all(_get_backend(), datasets, dataset_meta)


@router.post("/storage/pull")
async def pull_all():
    from core.storage_backends import sync_pull_all
    return sync_pull_all(_get_backend())


@router.get("/storage/list-remote")
async def list_remote():
    try:
        remote = _get_backend().list_remote()
        return {"remote_datasets": remote, "count": len(remote)}
    except Exception as exc:
        raise HTTPException(500, f"Error listando archivos remotos: {exc}")


@router.post("/storage/push/{dataset_id}")
async def push_one(dataset_id: str, body: dict = {}):
    from core.store import dataset_meta
    from routers.export_analysis import ALL_SECTIONS as _AS
    formats  = body.get("formats", ["parquet"])
    sections = body.get("sections", list(_AS))
    invalid  = [f for f in formats if f not in ALL_FORMATS]
    if invalid:
        raise HTTPException(400, f"Formatos inválidos: {invalid}. Válidos: {ALL_FORMATS}")
    backend   = _get_backend()
    meta      = dataset_meta.get(dataset_id, {})
    safe_name = meta.get("name", dataset_id).replace(".csv", "").replace(" ", "_")
    results   = [_push_format(backend, dataset_id, f, sections, safe_name) for f in formats]
    return {
        "dataset_id": dataset_id,
        "pushed":     [r for r in results if not r.get("error")],
        "errors":     [r for r in results if r.get("error")],
        "formats_requested": formats,
    }


@router.post("/storage/pull/{dataset_id}")
async def pull_one(dataset_id: str):
    from core.store import register
    backend = _get_backend()
    try:
        df, meta = backend.pull(dataset_id)
        info = register(df, meta.get("name", dataset_id), dataset_id=dataset_id)
        return {"pulled": info}
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc))
    except Exception as exc:
        raise HTTPException(500, f"Error descargando dataset: {exc}")