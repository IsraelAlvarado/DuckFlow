"""
routers/stats.py — Statistical analysis endpoint.

Endpoints:
  POST /api/v1/stats/{id}

body.test options:
  outliers   {column, method: iqr|zscore, threshold?}
  normality  {column}                        → Shapiro-Wilk
  ttest      {column, column2?} | {column, group_column}
  chi2       {column1, column2}
  anova      {column, group_column}
"""
from __future__ import annotations

import numpy as np
from fastapi import APIRouter, HTTPException

from core.store import require_dataset

try:
    from scipy import stats as scipy_stats
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

router = APIRouter()


@router.post("/stats/{dataset_id}")
async def statistical_analysis(dataset_id: str, body: dict):
    if not SCIPY_AVAILABLE:
        raise HTTPException(503, "scipy no instalado. Ejecuta: pip install scipy")

    df = require_dataset(dataset_id)
    test = body.get("test", "")

    try:
        # ── Outlier detection ─────────────────────────────────────────
        if test == "outliers":
            col = body.get("column")
            method = body.get("method", "iqr")
            if not col or col not in df.columns:
                raise HTTPException(400, f"Columna '{col}' no encontrada.")
            series = df[col].dropna()
            threshold = float(body.get("threshold", 1.5 if method == "iqr" else 3.0))

            if method == "iqr":
                q1, q3 = series.quantile(0.25), series.quantile(0.75)
                iqr = q3 - q1
                lower, upper = q1 - threshold * iqr, q3 + threshold * iqr
                mask = (df[col] < lower) | (df[col] > upper)
            else:
                z = np.abs((series - series.mean()) / series.std())
                outlier_idx = series.index[z > threshold]
                mask = df.index.isin(outlier_idx)
                lower = float(series.mean() - threshold * series.std())
                upper = float(series.mean() + threshold * series.std())

            return {
                "test": "outliers", "column": col, "method": method,
                "threshold": threshold,
                "n_total": len(df), "n_outliers": int(mask.sum()),
                "pct_outliers": round(float(mask.sum() / len(df) * 100), 2),
                "lower_bound": round(float(lower), 4),
                "upper_bound": round(float(upper), 4),
                "sample_outliers": [round(float(v), 4) for v in df.loc[mask, col].head(100).tolist()],
                "stats": {
                    "min": round(float(series.min()), 4),
                    "q1": round(float(series.quantile(0.25)), 4),
                    "median": round(float(series.median()), 4),
                    "q3": round(float(series.quantile(0.75)), 4),
                    "max": round(float(series.max()), 4),
                },
            }

        # ── Normality (Shapiro-Wilk) ──────────────────────────────────
        elif test == "normality":
            col = body.get("column")
            if not col or col not in df.columns:
                raise HTTPException(400, f"Columna '{col}' no encontrada.")
            series = df[col].dropna()
            if len(series) > 5000:
                series = series.sample(5000, random_state=42)
            if len(series) < 3:
                raise HTTPException(400, "Se necesitan al menos 3 valores.")
            stat, p = scipy_stats.shapiro(series)
            return {
                "test": "normality", "column": col, "n": len(series),
                "statistic": round(float(stat), 6),
                "p_value": round(float(p), 6),
                "normal": bool(p > 0.05),
                "skewness": round(float(series.skew()), 4),
                "kurtosis": round(float(series.kurtosis()), 4),
                "interpretation": (
                    "La distribución parece normal (p > 0.05)."
                    if p > 0.05
                    else "La distribución NO parece normal (p ≤ 0.05)."
                ),
            }

        # ── T-test ────────────────────────────────────────────────────
        elif test == "ttest":
            col = body.get("column")
            group_col = body.get("group_column")
            col2 = body.get("column2")
            if not col or col not in df.columns:
                raise HTTPException(400, f"Columna '{col}' no encontrada.")

            if group_col and group_col in df.columns:
                groups = df[group_col].dropna().unique()
                if len(groups) < 2:
                    raise HTTPException(400, "Se necesitan al menos 2 grupos.")
                g1_val, g2_val = groups[0], groups[1]
                g1 = df[df[group_col] == g1_val][col].dropna()
                g2 = df[df[group_col] == g2_val][col].dropna()
                stat, p = scipy_stats.ttest_ind(g1, g2)
                return {
                    "test": "t-test independiente", "column": col, "group_column": group_col,
                    "group_1": {"label": str(g1_val), "n": len(g1), "mean": round(float(g1.mean()), 4), "std": round(float(g1.std()), 4)},
                    "group_2": {"label": str(g2_val), "n": len(g2), "mean": round(float(g2.mean()), 4), "std": round(float(g2.std()), 4)},
                    "statistic": round(float(stat), 6),
                    "p_value": round(float(p), 6),
                    "significant": bool(p < 0.05),
                    "interpretation": "Diferencia significativa entre grupos (p<0.05)." if p < 0.05 else "Sin diferencia significativa (p≥0.05).",
                }
            elif col2 and col2 in df.columns:
                g1, g2 = df[col].dropna(), df[col2].dropna()
                stat, p = scipy_stats.ttest_ind(g1, g2)
                return {
                    "test": "t-test independiente",
                    "column_1": {"name": col, "n": len(g1), "mean": round(float(g1.mean()), 4), "std": round(float(g1.std()), 4)},
                    "column_2": {"name": col2, "n": len(g2), "mean": round(float(g2.mean()), 4), "std": round(float(g2.std()), 4)},
                    "statistic": round(float(stat), 6),
                    "p_value": round(float(p), 6),
                    "significant": bool(p < 0.05),
                    "interpretation": "Medias significativamente distintas (p<0.05)." if p < 0.05 else "Sin diferencia significativa de medias (p≥0.05).",
                }
            else:
                raise HTTPException(400, "Especifica 'group_column' o 'column2'.")

        # ── Chi-square ────────────────────────────────────────────────
        elif test == "chi2":
            col1 = body.get("column1")
            col2 = body.get("column2")
            if not col1 or not col2 or col1 not in df.columns or col2 not in df.columns:
                raise HTTPException(400, "Especifica 'column1' y 'column2' válidas.")
            import pandas as pd
            ct = pd.crosstab(df[col1], df[col2])
            chi2, p, dof, _ = scipy_stats.chi2_contingency(ct)
            return {
                "test": "chi-cuadrado", "column1": col1, "column2": col2,
                "table_shape": list(ct.shape),
                "statistic": round(float(chi2), 6),
                "p_value": round(float(p), 6),
                "degrees_of_freedom": int(dof),
                "significant": bool(p < 0.05),
                "interpretation": (
                    f"Dependencia estadísticamente significativa entre '{col1}' y '{col2}' (p<0.05)."
                    if p < 0.05
                    else f"Sin dependencia significativa entre '{col1}' y '{col2}' (p≥0.05)."
                ),
            }

        # ── One-way ANOVA ─────────────────────────────────────────────
        elif test == "anova":
            col = body.get("column")
            group_col = body.get("group_column")
            if not col or not group_col or col not in df.columns or group_col not in df.columns:
                raise HTTPException(400, "Especifica 'column' y 'group_column' válidas.")
            groups_data = [
                grp[col].dropna().tolist()
                for _, grp in df.groupby(group_col)
                if grp[col].dropna().shape[0] >= 2
            ]
            if len(groups_data) < 2:
                raise HTTPException(400, "Se necesitan al menos 2 grupos con datos.")
            stat, p = scipy_stats.f_oneway(*groups_data)
            return {
                "test": "ANOVA", "column": col, "group_column": group_col,
                "n_groups": df[group_col].nunique(),
                "statistic": round(float(stat), 6),
                "p_value": round(float(p), 6),
                "significant": bool(p < 0.05),
                "interpretation": (
                    "Al menos un grupo difiere significativamente (p<0.05)."
                    if p < 0.05
                    else "Sin diferencias significativas entre grupos (p≥0.05)."
                ),
                "group_stats": [
                    {
                        "group": str(name),
                        "n": int(grp[col].dropna().count()),
                        "mean": round(float(grp[col].mean()), 4),
                        "std": round(float(grp[col].std()), 4),
                    }
                    for name, grp in df.groupby(group_col)
                ][:20],
            }

        else:
            raise HTTPException(400, f"Test desconocido: '{test}'. Usa: outliers, normality, ttest, chi2, anova.")

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"Error en análisis estadístico: {exc}")