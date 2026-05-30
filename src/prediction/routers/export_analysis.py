"""
routers/export_analysis.py — Exportar análisis completo como .py o .ipynb

El archivo generado incluye DOS capas:
  1. Los resultados reales ya calculados (tablas, estadísticas) como comentarios
     o celdas Markdown, para que el archivo sea útil sin necesidad de ejecutarlo.
  2. El código reproducible que, al ejecutarse con los datos originales,
     regenera los mismos resultados.

Endpoints:
  POST /api/v1/export-analysis/{dataset_id}

Body:
  format   : "py" | "ipynb"
  sections : lista de secciones a incluir (todas por defecto)
             ["overview", "missing", "numeric", "categorical",
              "correlation", "distributions", "outliers", "normality"]
"""
from __future__ import annotations

import json
import io
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from core.store import dataset_meta, require_dataset

router = APIRouter()

ALL_SECTIONS = [
    "overview",
    "missing",
    "numeric",
    "categorical",
    "correlation",
    "distributions",
    "outliers",
    "normality",
]

# ── Utilidades seguras ────────────────────────────────────────────────

def _sf(v) -> Optional[float]:
    """Safe float: devuelve None si NaN o Inf."""
    try:
        f = float(v)
        return None if (np.isnan(f) or np.isinf(f)) else round(f, 4)
    except Exception:
        return None


def _fmt(v) -> str:
    r = _sf(v)
    return str(r) if r is not None else "N/A"


# ── Cálculo de resultados reales ──────────────────────────────────────

def _calc_overview(df: pd.DataFrame, name: str) -> Dict[str, Any]:
    return {
        "name":        name,
        "rows":        len(df),
        "cols":        len(df.columns),
        "duplicates":  int(df.duplicated().sum()),
        "nulls_total": int(df.isnull().sum().sum()),
        "dtypes":      {c: str(t) for c, t in df.dtypes.items()},
        "columns":     df.columns.tolist(),
    }


def _calc_missing(df: pd.DataFrame) -> List[Dict]:
    missing = df.isnull().sum()
    missing = missing[missing > 0].sort_values(ascending=False)
    return [
        {"column": c, "missing": int(v), "pct": round(v / len(df) * 100, 2)}
        for c, v in missing.items()
    ]


def _calc_numeric(df: pd.DataFrame) -> List[Dict]:
    num_cols = df.select_dtypes(include="number").columns.tolist()
    rows = []
    for col in num_cols:
        s = df[col].dropna()
        if len(s) == 0:
            continue
        rows.append({
            "column":   col,
            "count":    len(s),
            "nulls":    int(df[col].isnull().sum()),
            "mean":     _sf(s.mean()),
            "median":   _sf(s.median()),
            "std":      _sf(s.std()),
            "min":      _sf(s.min()),
            "max":      _sf(s.max()),
            "q25":      _sf(s.quantile(0.25)),
            "q75":      _sf(s.quantile(0.75)),
            "skewness": _sf(s.skew()),
            "kurtosis": _sf(s.kurtosis()),
        })
    return rows


def _calc_categorical(df: pd.DataFrame) -> List[Dict]:
    cat_cols = df.select_dtypes(include=["object", "category"]).columns.tolist()
    rows = []
    for col in cat_cols:
        vc = df[col].value_counts()
        rows.append({
            "column":    col,
            "unique":    int(df[col].nunique()),
            "nulls":     int(df[col].isnull().sum()),
            "top_value": str(vc.index[0]) if len(vc) > 0 else "",
            "top_count": int(vc.iloc[0]) if len(vc) > 0 else 0,
            "top_10":    [{"name": str(k), "value": int(v)} for k, v in vc.head(10).items()],
        })
    return rows


def _calc_correlation(df: pd.DataFrame) -> Optional[Dict]:
    num_cols = df.select_dtypes(include="number").columns.tolist()
    if len(num_cols) < 2:
        return None
    corr_df = df[num_cols].corr().round(3)
    return {
        "columns": num_cols,
        "matrix":  [[_sf(v) for v in row] for row in corr_df.values.tolist()],
    }


def _calc_outliers(df: pd.DataFrame) -> List[Dict]:
    num_cols = df.select_dtypes(include="number").columns.tolist()[:6]
    rows = []
    for col in num_cols:
        s = df[col].dropna()
        q1, q3 = s.quantile(0.25), s.quantile(0.75)
        iqr = q3 - q1
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        mask = (df[col] < lo) | (df[col] > hi)
        rows.append({
            "column":    col,
            "n_outliers": int(mask.sum()),
            "pct":        round(float(mask.sum()) / len(df) * 100, 2),
            "lower":      _sf(lo),
            "upper":      _sf(hi),
        })
    return rows


def _calc_normality(df: pd.DataFrame) -> List[Dict]:
    try:
        from scipy import stats as sp
    except ImportError:
        return []
    num_cols = df.select_dtypes(include="number").columns.tolist()[:6]
    rows = []
    for col in num_cols:
        s = df[col].dropna()
        if len(s) > 5000:
            s = s.sample(5000, random_state=42)
        if len(s) < 3:
            continue
        stat, p = sp.shapiro(s)
        rows.append({
            "column":    col,
            "n":         len(s),
            "statistic": round(float(stat), 5),
            "p_value":   round(float(p), 5),
            "normal":    bool(p > 0.05),
            "skewness":  _sf(df[col].dropna().skew()),
        })
    return rows


# ── Generadores de código (con resultados embebidos) ──────────────────

def _lines_overview(ov: Dict) -> List[str]:
    dtype_lines = "\n".join(f"#   {c:<30} {t}" for c, t in ov["dtypes"].items())
    return [
        "# =============================================================",
        f"# DATASET : {ov['name']}",
        f"# Exportado: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "# =============================================================",
        "#",
        "# ── RESULTADOS REALES (al momento de exportar) ───────────────",
        f"# Filas        : {ov['rows']:,}",
        f"# Columnas     : {ov['cols']}",
        f"# Duplicados   : {ov['duplicates']}",
        f"# Nulos totales: {ov['nulls_total']}",
        "#",
        "# Tipos de columna:",
        dtype_lines,
        "# =============================================================",
        "",
        "import pandas as pd",
        "import numpy as np",
        "import matplotlib.pyplot as plt",
        "import matplotlib",
        "matplotlib.rcParams['figure.dpi'] = 110",
        "matplotlib.rcParams['axes.spines.top'] = False",
        "matplotlib.rcParams['axes.spines.right'] = False",
        "",
        "# ── 1. CARGA Y RESUMEN GENERAL ────────────────────────────────",
        "# Ajusta la ruta al archivo según tu entorno:",
        f"# df = pd.read_csv('{ov['name']}')",
        "",
        f"print('Filas:    ', {ov['rows']})",
        f"print('Columnas: ', {ov['cols']})",
        f"print('Duplicados:', {ov['duplicates']})",
        f"print('Nulos totales:', {ov['nulls_total']})",
        "",
        "print(df.dtypes)",
        "",
    ]


def _lines_missing(missing: List[Dict]) -> List[str]:
    if not missing:
        return [
            "# ── 2. VALORES FALTANTES ──────────────────────────────────────",
            "# Resultado real: No hay valores faltantes en este dataset.",
            "",
        ]
    result_block = "\n".join(
        f"#   {r['column']:<30} {r['missing']:>8} nulos  ({r['pct']}%)"
        for r in missing
    )
    return [
        "# ── 2. VALORES FALTANTES ──────────────────────────────────────",
        "# Resultado real:",
        result_block,
        "#",
        "missing = df.isnull().sum()",
        "missing_pct = (missing / len(df) * 100).round(2)",
        "missing_df = pd.DataFrame({'Nulos': missing, 'Porcentaje': missing_pct})",
        "missing_df = missing_df[missing_df['Nulos'] > 0].sort_values('Nulos', ascending=False)",
        "print(missing_df)",
        "",
        "fig, ax = plt.subplots(figsize=(8, max(3, len(missing_df) * 0.4)))",
        "missing_df['Porcentaje'].plot(kind='barh', ax=ax, color='#ef4444')",
        "ax.set_xlabel('% Nulos')",
        "ax.set_title('Porcentaje de valores faltantes por columna')",
        "plt.tight_layout()",
        "plt.show()",
        "",
    ]


def _lines_numeric(stats: List[Dict]) -> List[str]:
    if not stats:
        return ["# ── 3. ESTADÍSTICAS NUMÉRICAS — sin columnas numéricas\n"]

    hdr  = f"# {'Columna':<22} {'Media':>10} {'Mediana':>10} {'Std':>10} {'Min':>10} {'Max':>10} {'Sesgo':>8}"
    rows = "\n".join(
        f"# {r['column']:<22} {_fmt(r['mean']):>10} {_fmt(r['median']):>10} "
        f"{_fmt(r['std']):>10} {_fmt(r['min']):>10} {_fmt(r['max']):>10} {_fmt(r['skewness']):>8}"
        for r in stats
    )
    num_cols = [r["column"] for r in stats]
    return [
        "# ── 3. ESTADÍSTICAS NUMÉRICAS ────────────────────────────────",
        "# Resultado real:",
        hdr,
        rows,
        "#",
        f"num_cols = {num_cols}",
        "print(df[num_cols].describe().T.round(4))",
        "",
        "skew_kurt = pd.DataFrame({",
        "    'Asimetría': df[num_cols].skew().round(4),",
        "    'Curtosis':  df[num_cols].kurtosis().round(4),",
        "})",
        "print(skew_kurt)",
        "",
    ]


def _lines_categorical(stats: List[Dict]) -> List[str]:
    if not stats:
        return ["# ── 4. ESTADÍSTICAS CATEGÓRICAS — sin columnas categóricas\n"]
    result_block = "\n".join(
        f"# {r['column']}: {r['unique']} únicos | top: '{r['top_value']}' ({r['top_count']}x)"
        for r in stats
    )
    cat_cols = [r["column"] for r in stats]
    lines = [
        "# ── 4. ESTADÍSTICAS CATEGÓRICAS ──────────────────────────────",
        "# Resultado real:",
        result_block,
        "#",
        f"cat_cols = {cat_cols}",
        "for col in cat_cols:",
        "    vc = df[col].value_counts()",
        "    print(f'\\n{col} — {df[col].nunique()} valores únicos')",
        "    print(vc.head(10).to_string())",
        "",
    ]
    if len(cat_cols) <= 4:
        lines += [
            "fig, axes = plt.subplots(1, len(cat_cols), figsize=(5 * len(cat_cols), 4))",
            "if len(cat_cols) == 1: axes = [axes]",
            "for ax, col in zip(axes, cat_cols):",
            "    df[col].value_counts().head(10).plot(kind='bar', ax=ax, color='#3b82f6')",
            "    ax.set_title(col)",
            "    ax.set_xlabel('')",
            "    ax.tick_params(axis='x', rotation=45)",
            "plt.tight_layout()",
            "plt.show()",
            "",
        ]
    return lines


def _lines_correlation(corr: Optional[Dict]) -> List[str]:
    if not corr:
        return ["# ── 5. CORRELACIÓN — se necesitan ≥2 columnas numéricas\n"]

    num_cols = corr["columns"]
    # Mostrar top correlaciones como comentario
    pairs = []
    m = corr["matrix"]
    for i in range(len(num_cols)):
        for j in range(i + 1, len(num_cols)):
            v = m[i][j]
            if v is not None:
                pairs.append((abs(v), num_cols[i], num_cols[j], v))
    pairs.sort(reverse=True)
    top_pairs = "\n".join(
        f"#   {a:<25} <-> {b:<25} r={v:>7}"
        for _, a, b, v in pairs[:10]
    ) if pairs else "#   (sin pares calculables)"

    return [
        "# ── 5. MATRIZ DE CORRELACIÓN ─────────────────────────────────",
        "# Top correlaciones reales:",
        top_pairs,
        "#",
        f"num_cols = {num_cols}",
        "corr = df[num_cols].corr().round(3)",
        "print(corr)",
        "",
        "import matplotlib.pyplot as plt",
        "import numpy as np",
        f"fig, ax = plt.subplots(figsize=({max(6, len(num_cols))}, {max(5, len(num_cols))}))",
        "im = ax.imshow(corr.values, cmap='coolwarm', vmin=-1, vmax=1, aspect='auto')",
        "ax.set_xticks(range(len(num_cols)))",
        "ax.set_yticks(range(len(num_cols)))",
        "ax.set_xticklabels(num_cols, rotation=45, ha='right', fontsize=9)",
        "ax.set_yticklabels(num_cols, fontsize=9)",
        "for i in range(len(num_cols)):",
        "    for j in range(len(num_cols)):",
        "        ax.text(j, i, f'{corr.values[i, j]:.2f}', ha='center', va='center', fontsize=8)",
        "plt.colorbar(im, ax=ax, shrink=0.8)",
        "ax.set_title('Matriz de correlación de Pearson')",
        "plt.tight_layout()",
        "plt.show()",
        "",
    ]


def _lines_distributions(df: pd.DataFrame) -> List[str]:
    num_cols = df.select_dtypes(include="number").columns.tolist()[:8]
    if not num_cols:
        return ["# ── 6. DISTRIBUCIONES — sin columnas numéricas\n"]
    # Estadísticas de forma reales
    dist_summary = "\n".join(
        f"#   {c:<25} sesgo={_fmt(df[c].skew()):>8}  kurt={_fmt(df[c].kurtosis()):>8}"
        for c in num_cols
    )
    n = len(num_cols)
    ncols = min(n, 3)
    nrows = (n + ncols - 1) // ncols
    return [
        "# ── 6. DISTRIBUCIONES ────────────────────────────────────────",
        "# Resumen de forma (valores reales):",
        dist_summary,
        "#",
        f"num_cols = {num_cols}",
        f"fig, axes = plt.subplots({nrows}, {ncols}, figsize=({ncols * 4}, {nrows * 3}))",
        f"axes = np.array(axes).flatten()" if n > 1 else "axes = [axes]",
        "for ax, col in zip(axes, num_cols):",
        "    data = df[col].dropna()",
        "    ax.hist(data, bins=25, color='#3b82f6', edgecolor='white', linewidth=0.4)",
        "    ax.axvline(data.mean(),   color='#ef4444', linestyle='--', linewidth=1.2, label='Media')",
        "    ax.axvline(data.median(), color='#f59e0b', linestyle=':',  linewidth=1.2, label='Mediana')",
        "    ax.set_title(col, fontsize=10)",
        "    ax.legend(fontsize=7)",
        "for ax in axes[len(num_cols):]:",
        "    ax.set_visible(False)",
        "plt.suptitle('Distribuciones de variables numéricas', fontsize=12, y=1.01)",
        "plt.tight_layout()",
        "plt.show()",
        "",
    ]


def _lines_outliers(outlier_data: List[Dict]) -> List[str]:
    if not outlier_data:
        return ["# ── 7. DETECCIÓN DE OUTLIERS — sin columnas numéricas\n"]
    result_block = "\n".join(
        f"#   {r['column']:<25} {r['n_outliers']:>6} outliers  ({r['pct']}%)  "
        f"límites: [{_fmt(r['lower'])}, {_fmt(r['upper'])}]"
        for r in outlier_data
    )
    num_cols = [r["column"] for r in outlier_data]
    return [
        "# ── 7. DETECCIÓN DE OUTLIERS (IQR) ───────────────────────────",
        "# Resultado real:",
        result_block,
        "#",
        f"num_cols = {num_cols}",
        "outlier_summary = []",
        "for col in num_cols:",
        "    q1 = df[col].quantile(0.25)",
        "    q3 = df[col].quantile(0.75)",
        "    iqr = q3 - q1",
        "    lower = q1 - 1.5 * iqr",
        "    upper = q3 + 1.5 * iqr",
        "    mask = (df[col] < lower) | (df[col] > upper)",
        "    outlier_summary.append({'Columna': col, 'N_Outliers': int(mask.sum()),",
        "        'Pct': round(mask.sum() / len(df) * 100, 2),",
        "        'Límite_inf': round(lower, 4), 'Límite_sup': round(upper, 4)})",
        "outlier_df = pd.DataFrame(outlier_summary)",
        "print(outlier_df.to_string(index=False))",
        "",
        f"fig, axes = plt.subplots(1, len(num_cols), figsize=({len(num_cols) * 3}, 4))",
        "if len(num_cols) == 1: axes = [axes]",
        "for ax, col in zip(axes, num_cols):",
        "    ax.boxplot(df[col].dropna(), patch_artist=True,",
        "               boxprops=dict(facecolor='#eff6ff', color='#3b82f6'),",
        "               medianprops=dict(color='#ef4444', linewidth=2),",
        "               flierprops=dict(marker='o', color='#f59e0b', markersize=4))",
        "    ax.set_title(col, fontsize=9)",
        "plt.suptitle('Boxplots — detección de outliers', fontsize=11)",
        "plt.tight_layout()",
        "plt.show()",
        "",
    ]


def _lines_normality(norm_data: List[Dict]) -> List[str]:
    if not norm_data:
        return ["# ── 8. TEST DE NORMALIDAD — sin datos disponibles\n"]
    result_block = "\n".join(
        f"#   {r['column']:<25} W={r['statistic']:<10}  p={r['p_value']:<10}  "
        f"normal={'Sí' if r['normal'] else 'No'}  sesgo={_fmt(r['skewness'])}"
        for r in norm_data
    )
    num_cols = [r["column"] for r in norm_data]
    return [
        "# ── 8. TEST DE NORMALIDAD (Shapiro-Wilk) ────────────────────",
        "# Resultados reales:",
        result_block,
        "#",
        "from scipy import stats as sp",
        f"num_cols = {num_cols}",
        "normality_results = []",
        "for col in num_cols:",
        "    s = df[col].dropna()",
        "    if len(s) > 5000:",
        "        s = s.sample(5000, random_state=42)",
        "    if len(s) < 3:",
        "        continue",
        "    stat, p = sp.shapiro(s)",
        "    normality_results.append({'Columna': col, 'Estadístico': round(stat, 5),",
        "        'p_valor': round(p, 5), 'Normal': p > 0.05, 'Asimetría': round(float(s.skew()), 4)})",
        "norm_df = pd.DataFrame(normality_results)",
        "print(norm_df.to_string(index=False))",
        "",
    ]


# ── Ensamblado ────────────────────────────────────────────────────────

def _build_py_script(df: pd.DataFrame, name: str, sections: List[str]) -> str:
    """Genera el script .py con resultados reales embebidos como comentarios."""
    ov       = _calc_overview(df, name)
    missing  = _calc_missing(df)
    num_s    = _calc_numeric(df)
    cat_s    = _calc_categorical(df)
    corr     = _calc_correlation(df)
    outl     = _calc_outliers(df)
    norm     = _calc_normality(df)

    section_map = {
        "overview":      lambda: _lines_overview(ov),
        "missing":       lambda: _lines_missing(missing),
        "numeric":       lambda: _lines_numeric(num_s),
        "categorical":   lambda: _lines_categorical(cat_s),
        "correlation":   lambda: _lines_correlation(corr),
        "distributions": lambda: _lines_distributions(df),
        "outliers":      lambda: _lines_outliers(outl),
        "normality":     lambda: _lines_normality(norm),
    }

    all_lines: List[str] = []
    for sec in ALL_SECTIONS:
        if sec in sections:
            all_lines.extend(section_map[sec]())

    return "\n".join(all_lines)


def _build_ipynb(df: pd.DataFrame, name: str, sections: List[str]) -> dict:
    """Genera un notebook nbformat 4 con celdas Markdown de resultados + celdas de código."""
    ov       = _calc_overview(df, name)
    missing  = _calc_missing(df)
    num_s    = _calc_numeric(df)
    cat_s    = _calc_categorical(df)
    corr     = _calc_correlation(df)
    outl     = _calc_outliers(df)
    norm     = _calc_normality(df)

    section_code_map = {
        "overview":      lambda: _lines_overview(ov),
        "missing":       lambda: _lines_missing(missing),
        "numeric":       lambda: _lines_numeric(num_s),
        "categorical":   lambda: _lines_categorical(cat_s),
        "correlation":   lambda: _lines_correlation(corr),
        "distributions": lambda: _lines_distributions(df),
        "outliers":      lambda: _lines_outliers(outl),
        "normality":     lambda: _lines_normality(norm),
    }

    # Resultados en Markdown para cada sección
    section_results_md: Dict[str, List[str]] = {
        "overview": [
            f"### Resumen general\n",
            f"| Métrica | Valor |\n|---|---|\n",
            f"| Filas | {ov['rows']:,} |\n",
            f"| Columnas | {ov['cols']} |\n",
            f"| Duplicados | {ov['duplicates']} |\n",
            f"| Nulos totales | {ov['nulls_total']} |\n",
        ],
        "missing": (
            ["### Valores faltantes\n\n> Sin valores faltantes.\n"]
            if not missing else
            ["### Valores faltantes\n\n| Columna | Nulos | % |\n|---|---|---|\n"]
            + [f"| {r['column']} | {r['missing']} | {r['pct']}% |\n" for r in missing]
        ),
        "numeric": (
            ["### Estadísticas numéricas\n\n> Sin columnas numéricas.\n"]
            if not num_s else
            ["### Estadísticas numéricas\n\n| Columna | Media | Mediana | Std | Min | Max | Sesgo |\n|---|---|---|---|---|---|---|\n"]
            + [f"| {r['column']} | {_fmt(r['mean'])} | {_fmt(r['median'])} | {_fmt(r['std'])} "
               f"| {_fmt(r['min'])} | {_fmt(r['max'])} | {_fmt(r['skewness'])} |\n"
               for r in num_s]
        ),
        "categorical": (
            ["### Estadísticas categóricas\n\n> Sin columnas categóricas.\n"]
            if not cat_s else
            ["### Estadísticas categóricas\n\n| Columna | Únicos | Valor top | Frecuencia |\n|---|---|---|---|\n"]
            + [f"| {r['column']} | {r['unique']} | {r['top_value']} | {r['top_count']} |\n"
               for r in cat_s]
        ),
        "correlation": (
            ["### Correlación\n\n> Se necesitan ≥2 columnas numéricas.\n"]
            if not corr else
            _build_corr_md(corr)
        ),
        "distributions": [
            "### Distribuciones\n\n"
            + "| Columna | Sesgo | Curtosis |\n|---|---|---|\n"
            + "".join(
                f"| {c} | {_fmt(df[c].skew())} | {_fmt(df[c].kurtosis())} |\n"
                for c in df.select_dtypes(include="number").columns.tolist()[:8]
            )
        ],
        "outliers": (
            ["### Outliers (IQR)\n\n> Sin columnas numéricas.\n"]
            if not outl else
            ["### Outliers (IQR)\n\n| Columna | N Outliers | % | Lím. inf | Lím. sup |\n|---|---|---|---|---|\n"]
            + [f"| {r['column']} | {r['n_outliers']} | {r['pct']}% | {_fmt(r['lower'])} | {_fmt(r['upper'])} |\n"
               for r in outl]
        ),
        "normality": (
            ["### Normalidad (Shapiro-Wilk)\n\n> Sin datos de normalidad.\n"]
            if not norm else
            ["### Normalidad (Shapiro-Wilk)\n\n| Columna | W | p-valor | Normal | Sesgo |\n|---|---|---|---|---|\n"]
            + [f"| {r['column']} | {r['statistic']} | {r['p_value']} | {'Sí' if r['normal'] else 'No'} | {_fmt(r['skewness'])} |\n"
               for r in norm]
        ),
    }

    section_titles = {
        "overview":      "Resumen General",
        "missing":       "Valores Faltantes",
        "numeric":       "Estadísticas Numéricas",
        "categorical":   "Estadísticas Categóricas",
        "correlation":   "Correlación",
        "distributions": "Distribuciones",
        "outliers":      "Detección de Outliers",
        "normality":     "Test de Normalidad",
    }

    cells = []

    # Celda de título
    cells.append({
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            f"# Análisis de datos — {name}\n",
            f"**Exportado:** {datetime.now().strftime('%Y-%m-%d %H:%M')}  \n",
            f"**Filas:** {ov['rows']:,} | **Columnas:** {ov['cols']}  \n",
            f"**Duplicados:** {ov['duplicates']} | **Nulos totales:** {ov['nulls_total']}\n",
            "\n---\n",
            "> Este notebook incluye los **resultados reales** calculados al momento de exportar "
            "y el **código reproducible** para regenerarlos con los datos originales.\n",
        ],
    })

    for sec in ALL_SECTIONS:
        if sec not in sections:
            continue

        # Celda Markdown con resultados reales
        cells.append({
            "cell_type": "markdown",
            "metadata": {},
            "source": [f"## {section_titles[sec]}\n\n"] + section_results_md.get(sec, []),
        })

        # Celda de código reproducible
        lines = section_code_map[sec]()
        # Filtrar las líneas de comentario de "resultado real" para no duplicar
        code_lines = [l for l in lines if not l.startswith("# ──")]
        source = [l + "\n" for l in code_lines[:-1]] + ([code_lines[-1]] if code_lines else [])

        cells.append({
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": source,
        })

    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.10.0"},
        },
        "cells": cells,
    }


def _build_corr_md(corr: Dict) -> List[str]:
    cols = corr["columns"]
    m = corr["matrix"]
    pairs = sorted(
        [(abs(m[i][j] or 0), cols[i], cols[j], m[i][j])
         for i in range(len(cols)) for j in range(i + 1, len(cols))],
        reverse=True,
    )
    lines = ["### Correlación\n\nTop correlaciones:\n\n| Par | r |\n|---|---|\n"]
    for _, a, b, v in pairs[:10]:
        lines.append(f"| {a} ↔ {b} | {v} |\n")
    return lines


# ── Endpoint ───────────────────────────────────────────────────────────

@router.post("/export-analysis/{dataset_id}")
async def export_analysis(dataset_id: str, body: dict):
    """
    Genera y descarga el análisis completo del dataset como .py o .ipynb.
    Incluye resultados reales ya calculados + código reproducible.
    """
    fmt = body.get("format", "py").lower()
    if fmt not in ("py", "ipynb"):
        raise HTTPException(400, "El formato debe ser 'py' o 'ipynb'.")

    sections = body.get("sections", ALL_SECTIONS)
    sections = [s for s in ALL_SECTIONS if s in sections]
    if not sections:
        raise HTTPException(400, "Selecciona al menos una sección.")

    df   = require_dataset(dataset_id)
    name = dataset_meta.get(dataset_id, {}).get("name", dataset_id)
    safe = name.replace(".csv", "").replace(" ", "_")

    if fmt == "py":
        content  = _build_py_script(df, name, sections)
        buf      = io.BytesIO(content.encode("utf-8"))
        filename = f"analisis_{safe}.py"
        media    = "text/x-python"
    else:
        nb       = _build_ipynb(df, name, sections)
        content  = json.dumps(nb, ensure_ascii=False, indent=1)
        buf      = io.BytesIO(content.encode("utf-8"))
        filename = f"analisis_{safe}.ipynb"
        media    = "application/x-ipynb+json"

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )