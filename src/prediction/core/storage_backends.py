"""
core/storage_backends.py — Optional cloud storage backends.
"""
from __future__ import annotations

import io
import os
from abc import ABC, abstractmethod
from typing import Optional, Tuple

import pandas as pd


class StorageBackend(ABC):

    @abstractmethod
    def push(self, dataset_id: str, df: pd.DataFrame, meta: dict) -> str:
        pass

    @abstractmethod
    def pull(self, dataset_id: str) -> Tuple[pd.DataFrame, dict]:
        pass

    @abstractmethod
    def list_remote(self) -> list[dict]:
        pass

    @abstractmethod
    def delete_remote(self, dataset_id: str) -> None:
        pass


class GoogleDriveBackend(StorageBackend):

    MIME_PARQUET = "application/octet-stream"
    MIME_FOLDER  = "application/vnd.google-apps.folder"

    def __init__(self, folder_id: str):
        self.folder_id = folder_id
        self._svc = self._build_service()

    def _build_service(self):
        try:
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build
            import pickle

            SCOPES = ["https://www.googleapis.com/auth/drive"]
            token_path = "token.pickle"
            creds = None

            if os.path.exists(token_path):
                with open(token_path, "rb") as f:
                    creds = pickle.load(f)

            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    client_id     = os.getenv("GOOGLE_CLIENT_ID")
                    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
                    if not client_id or not client_secret:
                        raise RuntimeError(
                            "Define GOOGLE_CLIENT_ID y GOOGLE_CLIENT_SECRET en .env"
                        )
                    client_config = {
                        "installed": {
                            "client_id":                  client_id,
                            "client_secret":              client_secret,
                            "redirect_uris":              ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
                            "auth_uri":                   "https://accounts.google.com/o/oauth2/auth",
                            "token_uri":                  "https://oauth2.googleapis.com/token",
                            "auth_provider_x509_cert_url":"https://www.googleapis.com/oauth2/v1/certs",
                        }
                    }
                    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
                    creds = flow.run_local_server(port=0)

                with open(token_path, "wb") as f:
                    pickle.dump(creds, f)

            return build("drive", "v3", credentials=creds)

        except ImportError as e:
            raise RuntimeError(
                "Requiere: pip install google-auth-oauthlib google-api-python-client"
            ) from e

    def push(self, dataset_id: str, df: pd.DataFrame, meta: dict) -> str:
        from googleapiclient.http import MediaIoBaseUpload

        buf = io.BytesIO()
        df.to_parquet(buf, index=False, engine="pyarrow")
        buf.seek(0)

        fname = f"{dataset_id}.parquet"
        existing = self._find_file(fname)
        if existing:
            self._svc.files().update(
                fileId=existing,
                media_body=MediaIoBaseUpload(buf, mimetype=self.MIME_PARQUET),
                supportsAllDrives=True,
            ).execute()
            return existing
        else:
            file_meta = {
                "name": fname,
                "parents": [self.folder_id],
                "description": meta.get("name", ""),
            }
            result = self._svc.files().create(
                body=file_meta,
                media_body=MediaIoBaseUpload(buf, mimetype=self.MIME_PARQUET),
                fields="id",
                supportsAllDrives=True,
            ).execute()
            return result["id"]

    def pull(self, dataset_id: str) -> Tuple[pd.DataFrame, dict]:
        from googleapiclient.http import MediaIoBaseDownload

        fname = f"{dataset_id}.parquet"
        file_id = self._find_file(fname)
        if not file_id:
            raise FileNotFoundError(
                f"Dataset {dataset_id} not found in Google Drive folder.")

        request = self._svc.files().get_media(
            fileId=file_id,
            supportsAllDrives=True,
        )
        buf = io.BytesIO()
        dl = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = dl.next_chunk()
        buf.seek(0)
        df = pd.read_parquet(buf, engine="pyarrow")
        meta = {"id": dataset_id, "name": fname}
        return df, meta

    def list_remote(self) -> list[dict]:
        results = (
            self._svc.files()
            .list(
                q=f"'{self.folder_id}' in parents and trashed=false",
                fields="files(id, name, size, modifiedTime)",
                includeItemsFromAllDrives=True,
                supportsAllDrives=True,
            )
            .execute()
        )
        out = []
        for f in results.get("files", []):
            if f["name"].endswith(".parquet"):
                out.append({
                    "id":       f["name"].replace(".parquet", ""),
                    "name":     f["name"],
                    "drive_id": f["id"],
                    "size":     f.get("size"),
                    "modified": f.get("modifiedTime"),
                })
        return out

    def delete_remote(self, dataset_id: str) -> None:
        fname = f"{dataset_id}.parquet"
        file_id = self._find_file(fname)
        if file_id:
            self._svc.files().delete(
                fileId=file_id,
                supportsAllDrives=True,
            ).execute()

    def _find_file(self, fname: str) -> Optional[str]:
        results = (
            self._svc.files()
            .list(
                q=f"name='{fname}' and '{self.folder_id}' in parents "
                  "and trashed=false",
                fields="files(id)",
                includeItemsFromAllDrives=True,
                supportsAllDrives=True,
            )
            .execute()
        )
        files = results.get("files", [])
        return files[0]["id"] if files else None


class S3Backend(StorageBackend):

    def __init__(self, bucket: str, prefix: str = "datasets/",
                 endpoint: Optional[str] = None):
        self.bucket = bucket
        self.prefix = prefix.rstrip("/") + "/"
        try:
            import boto3
            kwargs = {}
            if endpoint:
                kwargs["endpoint_url"] = endpoint
            self._s3 = boto3.client("s3", **kwargs)
        except ImportError as e:
            raise RuntimeError("S3 backend requires: pip install boto3") from e

    def _key(self, dataset_id: str) -> str:
        return f"{self.prefix}{dataset_id}.parquet"

    def push(self, dataset_id: str, df: pd.DataFrame, meta: dict) -> str:
        buf = io.BytesIO()
        df.to_parquet(buf, index=False, engine="pyarrow")
        buf.seek(0)
        key = self._key(dataset_id)
        self._s3.put_object(
            Bucket=self.bucket, Key=key,
            Body=buf.read(),
            Metadata={"dataset_name": meta.get("name", "")},
        )
        return key

    def pull(self, dataset_id: str) -> Tuple[pd.DataFrame, dict]:
        key = self._key(dataset_id)
        obj = self._s3.get_object(Bucket=self.bucket, Key=key)
        buf = io.BytesIO(obj["Body"].read())
        df  = pd.read_parquet(buf, engine="pyarrow")
        meta = {
            "id":   dataset_id,
            "name": obj.get("Metadata", {}).get("dataset_name", key),
        }
        return df, meta

    def list_remote(self) -> list[dict]:
        paginator = self._s3.get_paginator("list_objects_v2")
        out = []
        for page in paginator.paginate(Bucket=self.bucket, Prefix=self.prefix):
            for obj in page.get("Contents", []):
                name = obj["Key"].replace(self.prefix, "")
                if name.endswith(".parquet"):
                    out.append({
                        "id":       name.replace(".parquet", ""),
                        "name":     name,
                        "size_kb":  round(obj["Size"] / 1024, 1),
                        "modified": str(obj["LastModified"]),
                    })
        return out

    def delete_remote(self, dataset_id: str) -> None:
        self._s3.delete_object(Bucket=self.bucket, Key=self._key(dataset_id))


def sync_push_all(backend: StorageBackend, local_datasets: dict,
                  local_meta: dict) -> dict:
    pushed, errors = [], []
    for did, df in local_datasets.items():
        try:
            uri = backend.push(did, df, local_meta.get(did, {}))
            pushed.append({"id": did, "uri": uri})
        except Exception as exc:
            errors.append({"id": did, "error": str(exc)})
    return {"pushed": pushed, "errors": errors}


def sync_pull_all(backend: StorageBackend) -> dict:
    from core.store import register

    pulled, errors = [], []
    for remote in backend.list_remote():
        try:
            df, meta = backend.pull(remote["id"])
            info = register(df, meta.get("name", remote["id"]),
                            dataset_id=remote["id"])
            pulled.append(info)
        except Exception as exc:
            errors.append({"id": remote["id"], "error": str(exc)})
    return {"pulled": pulled, "errors": errors}