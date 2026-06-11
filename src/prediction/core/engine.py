from __future__ import annotations

import io
from typing import Union

import pandas as pd

SUPPORTED_ENGINES: tuple[str, ...] = ("pandas", "polars")
DEFAULT_ENGINE = "pandas"


def _validate(engine: str) -> str:
    e = engine.lower().strip()
    if e not in SUPPORTED_ENGINES:
        raise ValueError(
            f"Engine '{engine}' no soportado. Usa: {', '.join(SUPPORTED_ENGINES)}"
        )
    return e


def read_csv(source: Union[str, bytes, io.BytesIO], engine: str = DEFAULT_ENGINE) -> pd.DataFrame:
    engine = _validate(engine)

    if engine == "polars":
        try:
            import polars as pl
        except ImportError as exc:
            raise ImportError(
                "Polars no instalado. Ejecuta: pip install polars"
            ) from exc

        if isinstance(source, bytes):
            source = io.BytesIO(source)

        return pl.read_csv(source, infer_schema_length=10_000, ignore_errors=True).to_pandas()

    if isinstance(source, bytes):
        source = io.BytesIO(source)
    return pd.read_csv(source)


def engine_label(engine: str) -> str:
    return {"pandas": "Pandas", "polars": "Polars"}.get(engine.lower(), engine)