"""
routers/merge.py — Dataset merge/join endpoint.

Endpoints:
  POST /api/v1/merge

Body keys:
  left_id   : str
  right_id  : str
  how       : inner | left | right | outer  (default: inner)
  on        : str | [str]
  left_on   : str | [str]
  right_on  : str | [str]
  save_as   : str
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from core.store import register, require_dataset

router = APIRouter()


@router.post("/merge")
async def merge_datasets(body: dict):
    left_id = body.get("left_id")
    right_id = body.get("right_id")

    df_left = require_dataset(left_id)
    df_right = require_dataset(right_id)

    kwargs: Dict[str, Any] = {"how": body.get("how", "inner")}
    if body.get("on"):
        kwargs["on"] = body["on"]
    elif body.get("left_on") and body.get("right_on"):
        kwargs["left_on"] = body["left_on"]
        kwargs["right_on"] = body["right_on"]
    else:
        raise HTTPException(400, "Especifica 'on' o 'left_on'/'right_on'.")

    try:
        df_merged = df_left.merge(df_right, **kwargs)
    except Exception as exc:
        raise HTTPException(500, f"Error en merge: {exc}")

    new_name = body.get("save_as") or "merged"
    info = register(df_merged, new_name)

    return {
        "new_dataset_id": info["id"],
        "result": info,
        "rows_before": {"left": len(df_left), "right": len(df_right)},
        "rows_after": len(df_merged),
    }