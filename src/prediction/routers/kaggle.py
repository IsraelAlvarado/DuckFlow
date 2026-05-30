"""
routers/kaggle.py — Kaggle integration endpoints.

Endpoints:
  GET  /api/v1/kaggle/search
  POST /api/v1/kaggle/download
  POST /api/v1/kaggle/upload
"""
from __future__ import annotations

import json as _json
import os
import re
import shutil
import subprocess
import tempfile

import pandas as pd
from fastapi import APIRouter, HTTPException

from core.kaggle_client import run_cmd
from core.store import register, require_dataset

router = APIRouter()


@router.get("/kaggle/search")
async def kaggle_search(q: str = ""):
    try:
        cmd = ["kaggle", "datasets", "list", "--csv", "--max-size", "1048576"]
        if q.strip():
            cmd += ["--search", q.strip()]
        r = run_cmd(cmd, timeout=30)
        if r.returncode != 0:
            raise HTTPException(400, r.stderr.strip() or "Error consultando Kaggle.")
        lines = [l for l in r.stdout.strip().splitlines() if l.strip()]
        if len(lines) < 2:
            return {"datasets": [], "query": q}
        headers = [h.strip() for h in lines[0].split(",")]
        results = []
        for line in lines[1:21]:
            vals = line.split(",")
            if len(vals) >= len(headers):
                results.append(dict(zip(headers, [v.strip() for v in vals])))
        return {"datasets": results, "query": q}
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "Timeout conectando con Kaggle.")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc))


@router.post("/kaggle/download")
async def kaggle_download(body: dict):
    ref = (body.get("dataset") or "").strip()
    if not ref or "/" not in ref:
        raise HTTPException(400, "Formato inválido. Usa 'propietario/slug'.")

    tmpdir = tempfile.mkdtemp(prefix="kaggle_dl_")
    try:
        cmd = ["kaggle", "datasets", "download", ref, "--path", tmpdir, "--unzip"]
        r = run_cmd(cmd, timeout=180)
        if r.returncode != 0:
            raise HTTPException(400, r.stderr.strip() or r.stdout.strip() or "Error descargando.")

        csv_paths: list[str] = []
        for root, _, files in os.walk(tmpdir):
            for f in files:
                if f.lower().endswith(".csv") and not f.startswith("."):
                    csv_paths.append(os.path.join(root, f))

        if not csv_paths:
            raise HTTPException(404, "El dataset no contiene archivos CSV.")

        loaded, errors = [], []
        for path in csv_paths:
            try:
                df = pd.read_csv(path)
                if not df.empty:
                    loaded.append(register(df, os.path.basename(path)))
            except Exception as exc:
                errors.append({"name": os.path.basename(path), "error": str(exc)})

        return {"loaded": loaded, "errors": errors, "source": ref}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


@router.post("/kaggle/upload")
async def kaggle_upload(body: dict):
    dataset_id = body.get("dataset_id")
    title = (body.get("title") or "uploaded-dataset").strip()
    slug = (body.get("slug") or re.sub(r"[^a-z0-9-]", "-", title.lower()).strip("-"))
    username = (body.get("username") or os.getenv("KAGGLE_USERNAME", "")).strip()
    new_version = bool(body.get("new_version", False))

    if not dataset_id:
        raise HTTPException(400, "dataset_id requerido.")
    if not username:
        raise HTTPException(400, "username requerido. Configura KAGGLE_USERNAME en .env.")

    df = require_dataset(dataset_id)
    tmpdir = tempfile.mkdtemp(prefix="kaggle_up_")
    try:
        csv_path = os.path.join(tmpdir, f"{slug}.csv")
        df.to_csv(csv_path, index=False)

        if new_version:
            cmd = ["kaggle", "datasets", "version", "-p", tmpdir, "-m", f"Actualización: {title}"]
        else:
            meta = {
                "title": title,
                "id": f"{username}/{slug}",
                "licenses": [{"name": "CC0-1.0"}],
            }
            with open(os.path.join(tmpdir, "dataset-metadata.json"), "w") as fh:
                _json.dump(meta, fh, indent=2)
            cmd = ["kaggle", "datasets", "create", "-p", tmpdir]
            if not body.get("is_public", False):
                cmd.append("--no-public")

        r = run_cmd(cmd, timeout=180)
        if r.returncode != 0:
            raise HTTPException(400, r.stderr.strip() or r.stdout.strip() or "Error subiendo a Kaggle.")

        return {
            "success": True,
            "message": r.stdout.strip(),
            "url": f"https://www.kaggle.com/datasets/{username}/{slug}",
        }
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)