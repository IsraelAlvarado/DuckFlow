"""
routers/train.py — Machine Learning training endpoint.

Endpoints:
  GET  /api/v1/train/models
  POST /api/v1/train/{dataset_id}
  POST /api/v1/train/{dataset_id}/shap   ← NUEVO: explicabilidad SHAP

body keys (train):
  target          : str
  task            : classification | regression
  models          : list[str]
  test_size       : float (0.05–0.5, default 0.2)
  sample_size     : int | null
  random_state    : int (default 42)
  scale_features  : bool (default true)
  cv_folds        : int (2–10, default 5)
  save_as         : str

body keys (shap):
  target          : str           — requerido
  task            : classification | regression
  model_id        : str           — modelo a explicar (default: mejor disponible)
  sample_size     : int           — filas a explicar (default: 200, max: 500)
  test_size       : float
  random_state    : int
  scale_features  : bool
  max_features    : int           — top N features en los gráficos (default: 15)
"""
from __future__ import annotations

import warnings
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException

from core.store import dataset_meta, make_id, register, require_dataset

warnings.filterwarnings("ignore")

router = APIRouter()

# ── Modelos disponibles ───────────────────────────────────────────────

CLASSIFICATION_MODELS = {
    "logistic_regression": {
        "label": "Regresion Logistica",
        "class": "sklearn.linear_model.LogisticRegression",
        "params": {"max_iter": 1000, "random_state": 42},
    },
    "random_forest": {
        "label": "Random Forest",
        "class": "sklearn.ensemble.RandomForestClassifier",
        "params": {"n_estimators": 100, "random_state": 42, "n_jobs": -1},
    },
    "gradient_boosting": {
        "label": "Gradient Boosting",
        "class": "sklearn.ensemble.GradientBoostingClassifier",
        "params": {"n_estimators": 100, "random_state": 42},
    },
    "decision_tree": {
        "label": "Arbol de Decision",
        "class": "sklearn.tree.DecisionTreeClassifier",
        "params": {"random_state": 42},
    },
    "knn": {
        "label": "K-Nearest Neighbors",
        "class": "sklearn.neighbors.KNeighborsClassifier",
        "params": {"n_neighbors": 5},
    },
    "svm": {
        "label": "SVM",
        "class": "sklearn.svm.SVC",
        "params": {"probability": True, "random_state": 42},
    },
}

REGRESSION_MODELS = {
    "linear_regression": {
        "label": "Regresion Lineal",
        "class": "sklearn.linear_model.LinearRegression",
        "params": {},
    },
    "ridge": {
        "label": "Ridge",
        "class": "sklearn.linear_model.Ridge",
        "params": {"random_state": 42},
    },
    "lasso": {
        "label": "Lasso",
        "class": "sklearn.linear_model.Lasso",
        "params": {"max_iter": 5000, "random_state": 42},
    },
    "random_forest": {
        "label": "Random Forest",
        "class": "sklearn.ensemble.RandomForestRegressor",
        "params": {"n_estimators": 100, "random_state": 42, "n_jobs": -1},
    },
    "gradient_boosting": {
        "label": "Gradient Boosting",
        "class": "sklearn.ensemble.GradientBoostingRegressor",
        "params": {"n_estimators": 100, "random_state": 42},
    },
    "decision_tree": {
        "label": "Arbol de Decision",
        "class": "sklearn.tree.DecisionTreeRegressor",
        "params": {"random_state": 42},
    },
}

# Modelos que admiten TreeExplainer (más rápido y exacto)
TREE_MODELS = {"random_forest", "gradient_boosting", "decision_tree"}
# Modelos lineales: LinearExplainer
LINEAR_MODELS = {"logistic_regression", "linear_regression", "ridge", "lasso"}

# ── Helpers ───────────────────────────────────────────────────────────

def _import_class(path: str):
    module_path, class_name = path.rsplit(".", 1)
    import importlib
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def _safe_float(v) -> Optional[float]:
    try:
        f = float(v)
        return None if (np.isnan(f) or np.isinf(f)) else round(f, 6)
    except Exception:
        return None


def _feature_importances(model, feature_names: List[str]) -> List[Dict]:
    importances = None
    if hasattr(model, "feature_importances_"):
        importances = model.feature_importances_
    elif hasattr(model, "coef_"):
        coef = model.coef_
        importances = np.abs(coef[0] if coef.ndim > 1 else coef)

    if importances is None:
        return []

    pairs = sorted(
        zip(feature_names, importances),
        key=lambda x: abs(x[1]),
        reverse=True,
    )
    total = sum(abs(v) for _, v in pairs) or 1.0
    return [
        {
            "feature": f,
            "importance": round(float(v), 6),
            "importance_pct": round(abs(float(v)) / total * 100, 2),
        }
        for f, v in pairs[:20]
    ]


def _train_single(
    ModelClass,
    params: dict,
    X_train, X_test, y_train, y_test,
    task: str,
    feature_names: List[str],
    cv_folds: int,
    label: str,
):
    from sklearn.model_selection import cross_val_score

    model = ModelClass(**params)
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)

    result: Dict[str, Any] = {"label": label}

    if task == "classification":
        from sklearn.metrics import (
            accuracy_score, f1_score, precision_score,
            recall_score, roc_auc_score, confusion_matrix,
        )
        result["accuracy"]  = _safe_float(accuracy_score(y_test, y_pred))
        result["f1"]        = _safe_float(f1_score(y_test, y_pred, average="weighted", zero_division=0))
        result["precision"] = _safe_float(precision_score(y_test, y_pred, average="weighted", zero_division=0))
        result["recall"]    = _safe_float(recall_score(y_test, y_pred, average="weighted", zero_division=0))

        try:
            if hasattr(model, "predict_proba"):
                proba = model.predict_proba(X_test)
                classes = np.unique(y_test)
                if len(classes) == 2:
                    result["roc_auc"] = _safe_float(roc_auc_score(y_test, proba[:, 1]))
                else:
                    result["roc_auc"] = _safe_float(
                        roc_auc_score(y_test, proba, multi_class="ovr", average="weighted")
                    )
        except Exception:
            result["roc_auc"] = None

        try:
            cm = confusion_matrix(y_test, y_pred)
            result["confusion_matrix"] = cm.tolist()
        except Exception:
            result["confusion_matrix"] = None

        try:
            cv_scores = cross_val_score(
                ModelClass(**params), X_train, y_train,
                cv=cv_folds, scoring="accuracy", n_jobs=-1
            )
            result["cv_mean"] = _safe_float(cv_scores.mean())
            result["cv_std"]  = _safe_float(cv_scores.std())
        except Exception:
            result["cv_mean"] = result["cv_std"] = None

    else:
        from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

        result["r2"]   = _safe_float(r2_score(y_test, y_pred))
        result["mae"]  = _safe_float(mean_absolute_error(y_test, y_pred))
        result["rmse"] = _safe_float(np.sqrt(mean_squared_error(y_test, y_pred)))
        result["mape"] = _safe_float(
            np.mean(np.abs((y_test - y_pred) / np.where(y_test == 0, 1e-9, y_test))) * 100
        )

        try:
            cv_scores = cross_val_score(
                ModelClass(**params), X_train, y_train,
                cv=cv_folds, scoring="r2", n_jobs=-1
            )
            result["cv_mean"] = _safe_float(cv_scores.mean())
            result["cv_std"]  = _safe_float(cv_scores.std())
        except Exception:
            result["cv_mean"] = result["cv_std"] = None

    result["feature_importances"] = _feature_importances(model, feature_names)
    return result, model, y_pred


def _prepare_data(df: pd.DataFrame, target: str, task: str,
                  test_size: float, random_state: int,
                  scale: bool, sample_size: Optional[int] = None):
    """Preprocesamiento común para train y SHAP."""
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import StandardScaler, LabelEncoder

    if sample_size and sample_size < len(df):
        df = df.sample(n=sample_size, random_state=random_state)

    df = df.dropna(subset=[target])
    X_raw = df.drop(columns=[target])
    y_raw = df[target]

    X = pd.get_dummies(X_raw, drop_first=True)
    X = X.dropna(axis=1, how="all")
    X = X.fillna(X.median(numeric_only=True))
    zero_var = X.columns[X.std() == 0].tolist()
    if zero_var:
        X = X.drop(columns=zero_var)

    feature_names = X.columns.tolist()
    if not feature_names:
        raise HTTPException(400, "No quedan features validas despues del preprocesamiento.")

    le = None
    if task == "classification":
        le = LabelEncoder()
        y = le.fit_transform(y_raw.astype(str))
        classes = le.classes_.tolist()
    else:
        y = pd.to_numeric(y_raw, errors="coerce").fillna(y_raw.median()).values
        classes = []

    X_train, X_test, y_train, y_test = train_test_split(
        X.values, y,
        test_size=test_size,
        random_state=random_state,
        stratify=y if task == "classification" and len(np.unique(y)) <= 20 else None,
    )

    scaler = None
    if scale:
        scaler = StandardScaler()
        X_train = scaler.fit_transform(X_train)
        X_test  = scaler.transform(X_test)

    return X_train, X_test, y_train, y_test, feature_names, le, classes, scaler, X.values


# ── SHAP helpers ──────────────────────────────────────────────────────

def _get_shap_explainer(model, model_id: str, X_background, task: str):
    """
    Selecciona el explainer SHAP más adecuado:
    - TreeExplainer  → random_forest, gradient_boosting, decision_tree
    - LinearExplainer → regresión lineal, ridge, lasso, logistic_regression
    - KernelExplainer → resto (SVM, KNN) con muestra reducida de background
    """
    try:
        import shap
    except ImportError:
        raise HTTPException(503, "shap no instalado. Ejecuta: pip install shap")

    if model_id in TREE_MODELS:
        explainer = shap.TreeExplainer(model)
        explainer_type = "tree"
    elif model_id in LINEAR_MODELS:
        bg = shap.maskers.Independent(X_background, max_samples=100)
        explainer = shap.LinearExplainer(model, bg)
        explainer_type = "linear"
    else:
        # KernelExplainer: lento pero universal
        bg_sample = shap.sample(X_background, min(50, len(X_background)))
        if task == "classification" and hasattr(model, "predict_proba"):
            explainer = shap.KernelExplainer(model.predict_proba, bg_sample)
        else:
            explainer = shap.KernelExplainer(model.predict, bg_sample)
        explainer_type = "kernel"

    return explainer, explainer_type


def _compute_shap_values(explainer, X_explain, task: str, explainer_type: str):
    """
    Extrae la matriz de valores SHAP como array 2D (n_samples × n_features).
    Para clasificación multiclase devuelve los valores de la clase positiva (índice 1)
    o el promedio de clases.
    """
    raw = explainer.shap_values(X_explain)

    # TreeExplainer en clasificación puede devolver lista de arrays por clase
    if isinstance(raw, list):
        if len(raw) == 2:
            # clasificación binaria: tomar clase positiva
            shap_matrix = raw[1]
        else:
            # multiclase: promediar valor absoluto de todas las clases
            shap_matrix = np.mean([np.abs(r) for r in raw], axis=0)
    else:
        # regresión o kernel con output escalar
        if raw.ndim == 3:
            # (n_samples, n_features, n_classes) → clase positiva o promedio
            if raw.shape[2] == 2:
                shap_matrix = raw[:, :, 1]
            else:
                shap_matrix = np.mean(np.abs(raw), axis=2)
        else:
            shap_matrix = raw

    return shap_matrix


def _build_beeswarm_data(shap_matrix: np.ndarray, X_explain: np.ndarray,
                          feature_names: List[str], max_features: int) -> List[Dict]:
    """
    Datos para el gráfico beeswarm (summary plot).
    Devuelve top N features ordenadas por |SHAP| medio descendente.
    Cada feature incluye lista de puntos {shap, feature_value} para scatter.
    """
    mean_abs = np.mean(np.abs(shap_matrix), axis=0)
    top_idx  = np.argsort(mean_abs)[::-1][:max_features]

    result = []
    for idx in top_idx:
        feature_vals = X_explain[:, idx].tolist()
        shap_vals    = shap_matrix[:, idx].tolist()

        # Normalizar feature_vals a [0,1] para colorear por valor de feature
        fv_arr = np.array(feature_vals)
        fv_min, fv_max = fv_arr.min(), fv_arr.max()
        if fv_max > fv_min:
            fv_norm = ((fv_arr - fv_min) / (fv_max - fv_min)).tolist()
        else:
            fv_norm = [0.5] * len(fv_arr)

        # Submuestrear si hay demasiados puntos para el frontend
        n = len(shap_vals)
        if n > 200:
            idx_sample = np.random.choice(n, 200, replace=False)
            shap_vals    = [shap_vals[i]    for i in idx_sample]
            fv_norm      = [fv_norm[i]      for i in idx_sample]
            feature_vals = [feature_vals[i] for i in idx_sample]

        result.append({
            "feature":      feature_names[idx],
            "mean_abs":     round(float(mean_abs[idx]), 6),
            "shap_values":  [round(v, 5) for v in shap_vals],
            "feature_norm": [round(v, 4) for v in fv_norm],
            "feature_raw":  [round(float(v), 4) for v in feature_vals],
        })

    return result


def _build_waterfall_data(shap_matrix: np.ndarray, base_value: float,
                           feature_names: List[str], max_features: int,
                           sample_idx: int = 0) -> Dict:
    """
    Datos para el gráfico waterfall de una sola observación.
    Muestra cómo cada feature empuja la predicción desde el valor base.
    """
    shap_row = shap_matrix[sample_idx]

    # Ordenar por |shap| descendente, mostrar top N
    order = np.argsort(np.abs(shap_row))[::-1][:max_features]
    others_sum = float(np.sum(shap_row) - np.sum(shap_row[order]))

    bars = []
    cumulative = base_value
    for idx in order[::-1]:   # de menor a mayor impacto para apilar de abajo arriba
        v = float(shap_row[idx])
        bars.append({
            "feature": feature_names[idx],
            "shap":    round(v, 5),
            "start":   round(cumulative, 5),
            "end":     round(cumulative + v, 5),
            "positive": v >= 0,
        })
        cumulative += v

    if abs(others_sum) > 1e-6:
        bars.append({
            "feature":  "Otras features",
            "shap":     round(others_sum, 5),
            "start":    round(cumulative, 5),
            "end":      round(cumulative + others_sum, 5),
            "positive": others_sum >= 0,
        })
        cumulative += others_sum

    return {
        "base_value":       round(base_value, 5),
        "final_value":      round(cumulative, 5),
        "bars":             list(reversed(bars)),  # mayor impacto arriba
        "sample_index":     sample_idx,
    }


def _build_dependence_data(shap_matrix: np.ndarray, X_explain: np.ndarray,
                            feature_names: List[str], max_features: int) -> List[Dict]:
    """
    Datos para gráficos de dependencia SHAP: valor de feature vs SHAP value.
    Devuelve los top N features para que el frontend elija cuál graficar.
    """
    mean_abs = np.mean(np.abs(shap_matrix), axis=0)
    top_idx  = np.argsort(mean_abs)[::-1][:max_features]

    result = []
    for idx in top_idx:
        fv   = X_explain[:, idx]
        sv   = shap_matrix[:, idx]

        # Submuestrear
        n = len(fv)
        if n > 300:
            sel = np.random.choice(n, 300, replace=False)
            fv, sv = fv[sel], sv[sel]

        result.append({
            "feature":       feature_names[idx],
            "feature_vals":  [round(float(v), 4) for v in fv],
            "shap_vals":     [round(float(v), 5) for v in sv],
            "mean_abs":      round(float(mean_abs[idx]), 6),
        })
    return result


# ── Endpoints ─────────────────────────────────────────────────────────

@router.get("/train/models")
async def list_models():
    """Devuelve los modelos disponibles por tipo de tarea."""
    return {
        "classification": {k: v["label"] for k, v in CLASSIFICATION_MODELS.items()},
        "regression":     {k: v["label"] for k, v in REGRESSION_MODELS.items()},
    }


@router.post("/train/{dataset_id}")
async def train_models(dataset_id: str, body: dict):
    """Entrena modelos ML y devuelve metricas comparativas."""
    try:
        from sklearn.model_selection import train_test_split
        from sklearn.preprocessing import StandardScaler, LabelEncoder
    except ImportError:
        raise HTTPException(503, "scikit-learn no instalado. Ejecuta: pip install scikit-learn")

    target       = body.get("target")
    task         = body.get("task", "classification").lower()
    test_size    = float(body.get("test_size", 0.2))
    sample_size  = body.get("sample_size")
    random_state = int(body.get("random_state", 42))
    scale        = bool(body.get("scale_features", True))
    cv_folds     = max(2, min(10, int(body.get("cv_folds", 5))))
    save_as      = body.get("save_as")
    req_models   = body.get("models")

    if not target:
        raise HTTPException(400, "El campo 'target' es requerido.")
    if task not in ("classification", "regression"):
        raise HTTPException(400, "task debe ser 'classification' o 'regression'.")
    if not (0.05 <= test_size <= 0.5):
        raise HTTPException(400, "test_size debe estar entre 0.05 y 0.5.")

    df = require_dataset(dataset_id).copy()

    if target not in df.columns:
        raise HTTPException(400, f"Columna objetivo '{target}' no encontrada.")

    X_train, X_test, y_train, y_test, feature_names, le, classes, scaler, _ = _prepare_data(
        df, target, task, test_size, random_state, scale,
        sample_size=int(sample_size) if sample_size else None,
    )

    model_registry = CLASSIFICATION_MODELS if task == "classification" else REGRESSION_MODELS
    if req_models:
        model_registry = {k: v for k, v in model_registry.items() if k in req_models}
    if not model_registry:
        raise HTTPException(400, f"Ningun modelo valido.")

    results:       Dict[str, Any] = {}
    best_model     = None
    best_score     = -np.inf
    best_model_id  = None
    best_y_pred    = None
    primary_metric = "accuracy" if task == "classification" else "r2"

    for model_id, cfg in model_registry.items():
        try:
            ModelClass = _import_class(cfg["class"])
            metrics, fitted_model, y_pred = _train_single(
                ModelClass, dict(cfg["params"]),
                X_train, X_test, y_train, y_test,
                task, feature_names, cv_folds, cfg["label"],
            )
            results[model_id] = metrics
            # Guardar modelo entrenado para SHAP posterior
            results[model_id]["_model_object"] = fitted_model
            results[model_id]["_model_id_key"] = model_id
            score = metrics.get(primary_metric) or -np.inf
            if score > best_score:
                best_score    = score
                best_model    = fitted_model
                best_model_id = model_id
                best_y_pred   = y_pred
        except Exception as exc:
            results[model_id] = {"label": cfg["label"], "error": str(exc)}

    predictions_dataset_id = None
    if save_as and best_model is not None:
        pred_df = df.dropna(subset=[target]).copy()
        if len(pred_df) > (sample_size or len(pred_df)):
            pred_df = pred_df.sample(n=int(sample_size), random_state=random_state)
        if task == "classification" and le is not None:
            pred_df["prediction"] = le.inverse_transform(best_y_pred)
        else:
            pred_df["prediction"] = best_y_pred
        predictions_dataset_id = register(pred_df, save_as)["id"]

    # Guardar estado de entrenamiento en dataset_meta para acceso SHAP posterior
    _training_cache[dataset_id] = {
        "models":        {k: v for k, v in results.items() if "_model_object" in v},
        "feature_names": feature_names,
        "task":          task,
        "target":        target,
        "test_size":     test_size,
        "random_state":  random_state,
        "scale":         scale,
        "scaler":        scaler,
        "X_test":        X_test,
        "y_test":        y_test,
        "le":            le,
        "classes":       classes,
    }

    # Limpiar objetos internos de la respuesta JSON
    for k in results:
        results[k].pop("_model_object", None)
        results[k].pop("_model_id_key", None)

    ranked = sorted(
        [(mid, m) for mid, m in results.items() if "error" not in m],
        key=lambda x: x[1].get(primary_metric) or -np.inf,
        reverse=True,
    )

    return {
        "task":                   task,
        "target":                 target,
        "dataset_id":             dataset_id,
        "n_samples_total":        len(df),
        "n_features":             len(feature_names),
        "feature_names":          feature_names,
        "test_size":              test_size,
        "cv_folds":               cv_folds,
        "classes":                classes,
        "primary_metric":         primary_metric,
        "best_model":             best_model_id,
        "best_score":             _safe_float(best_score),
        "models":                 results,
        "ranking":                [{"model": mid, **m} for mid, m in ranked],
        "predictions_dataset_id": predictions_dataset_id,
        "shap_available":         True,
    }


# Cache en memoria para estado de entrenamiento (modelos ajustados + datos de test)
_training_cache: Dict[str, Any] = {}


@router.post("/train/{dataset_id}/shap")
async def compute_shap(dataset_id: str, body: dict):
    """
    Calcula valores SHAP para el modelo entrenado y devuelve datos
    estructurados para tres tipos de gráficos:
      - beeswarm: distribución de SHAP por feature (summary plot)
      - waterfall: contribución de cada feature para una observación concreta
      - dependence: relación valor_feature vs shap_value por feature
    """
    try:
        import shap as shap_lib
    except ImportError:
        raise HTTPException(503, "shap no instalado. Ejecuta: pip install shap")

    target       = body.get("target")
    task         = body.get("task", "classification").lower()
    model_id_req = body.get("model_id")
    sample_size  = min(int(body.get("sample_size", 200)), 500)
    test_size    = float(body.get("test_size", 0.2))
    random_state = int(body.get("random_state", 42))
    scale        = bool(body.get("scale_features", True))
    max_features = min(int(body.get("max_features", 15)), 30)
    sample_idx   = int(body.get("sample_index", 0))

    if not target:
        raise HTTPException(400, "El campo 'target' es requerido.")

    df = require_dataset(dataset_id).copy()
    if target not in df.columns:
        raise HTTPException(400, f"Columna objetivo '{target}' no encontrada.")

    # ── Obtener modelo entrenado (del cache o reentrenar) ─────────────
    cached = _training_cache.get(dataset_id)
    model_registry = CLASSIFICATION_MODELS if task == "classification" else REGRESSION_MODELS

    if cached and cached.get("task") == task and cached.get("target") == target:
        # Usar modelo del cache
        models_in_cache = cached["models"]
        if model_id_req and model_id_req in models_in_cache:
            chosen_id = model_id_req
        else:
            # Elegir el mejor disponible (el primero del cache = mejor)
            chosen_id = next(iter(models_in_cache), None)

        if chosen_id and chosen_id in models_in_cache:
            model        = models_in_cache[chosen_id]["_model_object"]
            feature_names = cached["feature_names"]
            X_test_raw   = cached["X_test"]
            scaler       = cached.get("scaler")
            le           = cached.get("le")
        else:
            cached = None  # forzar reentrenamiento

    if not cached:
        # Reentrenar con el modelo solicitado
        chosen_id = model_id_req or ("random_forest" if "random_forest" in model_registry else next(iter(model_registry)))
        if chosen_id not in model_registry:
            raise HTTPException(400, f"Modelo '{chosen_id}' no reconocido.")

        try:
            from sklearn.preprocessing import LabelEncoder
        except ImportError:
            raise HTTPException(503, "scikit-learn no instalado.")

        X_train, X_test_raw, y_train, y_test, feature_names, le, classes, scaler, _ = _prepare_data(
            df, target, task, test_size, random_state, scale,
            sample_size=None,
        )
        cfg        = model_registry[chosen_id]
        ModelClass = _import_class(cfg["class"])
        model      = ModelClass(**dict(cfg["params"]))
        model.fit(X_train, y_train)

    # ── Muestra para SHAP ─────────────────────────────────────────────
    n_available = len(X_test_raw)
    n_explain   = min(sample_size, n_available)
    np.random.seed(random_state)
    explain_idx = np.random.choice(n_available, n_explain, replace=False)
    X_explain   = X_test_raw[explain_idx]

    # ── Construir explainer y calcular SHAP ───────────────────────────
    try:
        explainer, explainer_type = _get_shap_explainer(model, chosen_id, X_test_raw, task)
        shap_matrix = _compute_shap_values(explainer, X_explain, task, explainer_type)
    except Exception as exc:
        raise HTTPException(500, f"Error calculando SHAP: {exc}")

    # Base value (expected value del modelo)
    try:
        ev = explainer.expected_value
        if isinstance(ev, (list, np.ndarray)):
            base_value = float(ev[1]) if len(ev) == 2 else float(np.mean(ev))
        else:
            base_value = float(ev)
    except Exception:
        base_value = 0.0

    # Clamp sample_idx al rango disponible
    sample_idx = min(sample_idx, n_explain - 1)

    # ── Construir datos para los tres gráficos ────────────────────────
    beeswarm   = _build_beeswarm_data(shap_matrix, X_explain, feature_names, max_features)
    waterfall  = _build_waterfall_data(shap_matrix, base_value, feature_names, max_features, sample_idx)
    dependence = _build_dependence_data(shap_matrix, X_explain, feature_names, max_features)

    # ── Ranking global de importancia por |SHAP| medio ────────────────
    mean_abs_all = np.mean(np.abs(shap_matrix), axis=0)
    global_importance = sorted(
        [
            {
                "feature":    feature_names[i],
                "mean_abs":   round(float(mean_abs_all[i]), 6),
                "importance_pct": round(float(mean_abs_all[i]) / (float(mean_abs_all.sum()) or 1) * 100, 2),
            }
            for i in range(len(feature_names))
        ],
        key=lambda x: x["mean_abs"],
        reverse=True,
    )[:max_features]

    model_label = model_registry.get(chosen_id, {}).get("label", chosen_id)

    return {
        "dataset_id":     dataset_id,
        "model_id":       chosen_id,
        "model_label":    model_label,
        "explainer_type": explainer_type,
        "task":           task,
        "target":         target,
        "n_explained":    n_explain,
        "base_value":     round(base_value, 5),
        "feature_names":  feature_names,
        "global_importance": global_importance,
        "beeswarm":       beeswarm,
        "waterfall":      waterfall,
        "dependence":     dependence,
    }