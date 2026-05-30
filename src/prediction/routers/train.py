"""
routers/train.py — Machine Learning training endpoint.

Endpoints:
  GET  /api/v1/train/models           ← PRIMERO (evita colision con /{dataset_id})
  POST /api/v1/train/{dataset_id}

body keys:
  target          : str           — columna objetivo (requerido)
  task            : classification | regression
  models          : list[str]     — subconjunto de modelos a entrenar
  test_size       : float (0.05–0.5, default 0.2)
  sample_size     : int | null    — filas a usar (null = todas)
  random_state    : int (default 42)
  scale_features  : bool (default true)
  cv_folds        : int (2–10, default 5)
  save_as         : str           — nombre del dataset de predicciones
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


# ── IMPORTANTE: /train/models DEBE ir antes de /train/{dataset_id} ────
# FastAPI evalua rutas en orden de registro. Si /{dataset_id} se registra
# primero, "models" se interpreta como un dataset_id y devuelve 404.

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

    if sample_size and isinstance(sample_size, int) and sample_size < len(df):
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

    if len(np.unique(y)) < 2:
        raise HTTPException(400, "El target debe tener al menos 2 valores distintos.")

    X_train, X_test, y_train, y_test = train_test_split(
        X.values, y,
        test_size=test_size,
        random_state=random_state,
        stratify=y if task == "classification" and len(np.unique(y)) <= 20 else None,
    )

    if scale:
        scaler = StandardScaler()
        X_train = scaler.fit_transform(X_train)
        X_test  = scaler.transform(X_test)

    model_registry = CLASSIFICATION_MODELS if task == "classification" else REGRESSION_MODELS
    if req_models:
        model_registry = {k: v for k, v in model_registry.items() if k in req_models}
    if not model_registry:
        raise HTTPException(400, f"Ningun modelo valido. Disponibles: {list(model_registry.keys())}")

    results: Dict[str, Any] = {}
    best_model    = None
    best_score    = -np.inf
    best_model_id = None
    best_y_pred   = None
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
        pred_df = df.copy()
        if task == "classification" and le is not None:
            pred_df["prediction"] = le.inverse_transform(best_y_pred)
        else:
            pred_df["prediction"] = best_y_pred
        predictions_dataset_id = register(pred_df, save_as)["id"]

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
        "n_samples_used":         len(X.values),
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
    }