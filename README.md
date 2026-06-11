# Data Analyzer — ETL & ML Platform

Plataforma de analisis exploratorio, limpieza, transformacion y entrenamiento de modelos ML sobre datasets CSV. Interfaz web construida con Svelte + backend FastAPI + almacenamiento persistente en DuckDB y Parquet.

---

## Caracteristicas

| Modulo | Descripcion |
|---|---|
| **Carga** | CSV individuales, multiples o desde archivos ZIP/RAR |
| **EDA** | Estadisticas descriptivas, correlaciones, distribuciones, muestra |
| **Limpieza** | Duplicados, nulos, filtros, renombrado, conversion de tipos |
| **Transformacion** | Escalado, encoding, binning, features de fecha, rolling, lag, pivot, concat |
| **Merge** | JOIN tipo SQL entre datasets (inner, left, right, outer) |
| **Entrenamiento ML** | Clasificacion y regresion con hasta 6 modelos en paralelo, validacion cruzada, importancia de features, matriz de confusion |
| **Graficas** | 10 tipos de visualizacion interactiva (ECharts) |
| **Kaggle** | Busqueda, descarga y publicacion de datasets |
| **Almacen** | Sincronizacion con Google Drive o S3/MinIO/R2 en multiples formatos |
| **Exportar analisis** | Script `.py` o Jupyter Notebook `.ipynb` con resultados reales embebidos |

---

## Requisitos

- Python `>=3.10`
- Node.js `>=18`
- pip

Dependencias Python principales:

```
fastapi
uvicorn
pandas
numpy
duckdb
pyarrow
scikit-learn
scipy
python-dotenv
pyyaml
kaggle
```

Dependencias opcionales segun el backend de almacenamiento elegido:

```
# Google Drive
google-auth-oauthlib
google-api-python-client

# S3 / MinIO / Cloudflare R2
boto3
```

---

## Estructura del proyecto

```
ETL/Power-Bi/
├── frontend/                  # Svelte + Vite
│   └── src/
│       ├── App.svelte
│       └── components/
│           ├── DatasetManager.svelte
│           ├── EdaPanel.svelte
│           ├── CleaningPanel.svelte
│           ├── TransformPanel.svelte
│           ├── MergePanel.svelte
│           ├── TrainPanel.svelte      ← ML
│           ├── KagglePanel.svelte
│           ├── StoragePanel.svelte
│           └── Chart.svelte
│
├── src/
│   └── prediction/            # FastAPI backend
│       ├── main.py
│       ├── core/
│       │   ├── store.py       # DuckDB + Parquet
│       │   ├── kaggle_client.py
│       │   └── storage_backends.py
│       └── routers/
│           ├── datasets.py
│           ├── eda.py
│           ├── clean.py
│           ├── transform.py
│           ├── merge.py
│           ├── train.py       ← ML
│           ├── stats.py
│           ├── kaggle.py
│           ├── storage.py
│           └── export_analysis.py
│
└── data/                      # Generado en tiempo de ejecucion (no versionado)
    ├── raw/
    ├── processed/
    └── datasets/
```

---

## Configuracion

Copia el archivo de ejemplo y completa los valores:

```bash
cp .env.example .env
```

Variables disponibles en `.env.example`:

```env
# Directorio de datos
DATA_DIR=data/datasets
DB_PATH=data/catalog.duckdb

# Fuentes ETL (pipeline.py)
DATASET_SOURCE_DIR=data/raw
DATASET_OUTPUT_DIR=data/processed

# Kaggle (opcional)
KAGGLE_USERNAME=<tu_usuario>
api_token_kaggle=<tu_token>

# Almacenamiento en nube (elige uno)
STORAGE_BACKEND=          # gdrive | s3 | dejar vacio

# Google Drive
GDRIVE_FOLDER_ID=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

# S3 / MinIO / Cloudflare R2
S3_BUCKET=
S3_PREFIX=datasets/
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
S3_ENDPOINT=              # solo para MinIO o R2
```

---

## Instalacion y ejecucion

### Backend

```bash
cd ETL/Power-Bi/src/prediction
pip install -r requirements.txt
uvicorn main:app --reload
```

### Frontend

```bash
cd ETL/Power-Bi/frontend
npm install
npm run dev
```

La API expone su documentacion automatica en `/docs` (Swagger UI).

---

## Modelos ML disponibles

### Clasificacion

| ID | Modelo |
|---|---|
| `logistic_regression` | Regresion Logistica |
| `random_forest` | Random Forest |
| `gradient_boosting` | Gradient Boosting |
| `decision_tree` | Arbol de Decision |
| `knn` | K-Nearest Neighbors |
| `svm` | SVM |

### Regresion

| ID | Modelo |
|---|---|
| `linear_regression` | Regresion Lineal |
| `ridge` | Ridge |
| `lasso` | Lasso |
| `random_forest` | Random Forest |
| `gradient_boosting` | Gradient Boosting |
| `decision_tree` | Arbol de Decision |

### Parametros del endpoint `/api/v1/train/{dataset_id}`

| Campo | Tipo | Default | Descripcion |
|---|---|---|---|
| `target` | string | — | Columna objetivo (requerido) |
| `task` | string | `classification` | `classification` o `regression` |
| `models` | list | todos | Subconjunto de IDs de modelos |
| `test_size` | float | `0.2` | Proporcion del conjunto de prueba (0.05–0.5) |
| `sample_size` | int\|null | `null` | Filas a usar; `null` = todas |
| `cv_folds` | int | `5` | Folds de validacion cruzada (2–10) |
| `scale_features` | bool | `true` | Aplica StandardScaler |
| `random_state` | int | `42` | Semilla de aleatoriedad |
| `save_as` | string | — | Nombre del dataset de predicciones generado |

---

## API — resumen de endpoints

```
GET    /api/v1/datasets
POST   /api/v1/upload-csv
POST   /api/v1/upload-archive
POST   /api/v1/extract-from-archive
DELETE /api/v1/datasets/{id}
GET    /api/v1/export/{id}

GET    /api/v1/eda/{id}
POST   /api/v1/clean/{id}
POST   /api/v1/transform/{id}
POST   /api/v1/merge
POST   /api/v1/stats/{id}
POST   /api/v1/train/{id}
GET    /api/v1/train/models

POST   /api/v1/export-analysis/{id}

GET    /api/v1/kaggle/search
POST   /api/v1/kaggle/download
POST   /api/v1/kaggle/upload

GET    /api/v1/storage/status
POST   /api/v1/storage/push
POST   /api/v1/storage/pull
GET    /api/v1/storage/list-remote
POST   /api/v1/storage/push/{id}
POST   /api/v1/storage/pull/{id}
```

---

## Tamaño de muestra en EDA

El endpoint `/api/v1/eda/{id}` acepta el parametro `sample_size` para limitar las filas analizadas. Util con datasets de mas de 500 000 registros.

El panel de entrenamiento ML ofrece tres modos:
- **Todas las filas** — usa el dataset completo
- **Cantidad fija** — numero exacto de filas (muestreadas aleatoriamente)
- **Porcentaje** — fraccion del total (5%–100%)

---

## Persistencia

Los datasets se almacenan en Parquet dentro de `data/datasets/` y se catalogan en DuckDB (`data/catalog.duckdb`). Sobreviven reinicios del servidor. Los archivos de datos no se versionan; solo se versiona el codigo.

---

## Licencia

MIT

## Link Vercel
https://duck-flow-two.vercel.app/

## Preview
<img width="2494" height="1246" alt="image" src="https://github.com/user-attachments/assets/602851ab-2a9e-4651-8afb-40e12663a232" />
<img width="2512" height="1033" alt="image" src="https://github.com/user-attachments/assets/f1110403-2b1a-49f8-a543-823f0eda168d" />
<img width="2460" height="1240" alt="image" src="https://github.com/user-attachments/assets/1cfed5d0-0670-48c9-a989-2a3c2825c9b7" />
<img width="2496" height="990" alt="image" src="https://github.com/user-attachments/assets/07a2e114-3b70-47f0-97c1-4fe7ab5b295e" />
<img width="2505" height="1267" alt="image" src="https://github.com/user-attachments/assets/c54ed7fc-df71-4e3e-8cec-fb12ccbc18d6" />
<img width="2152" height="1292" alt="image" src="https://github.com/user-attachments/assets/9fc7e434-bebe-426a-bbd8-a0697ca1981e" />
<img width="2496" height="1220" alt="image" src="https://github.com/user-attachments/assets/6d5e057d-8468-44e0-b061-327ad80ee809" />
<img width="2067" height="1208" alt="image" src="https://github.com/user-attachments/assets/f6ca0629-ea84-48e1-9552-2ff58639fb5b" />
<img width="2510" height="1027" alt="image" src="https://github.com/user-attachments/assets/034218bf-70fc-451e-ab97-8ee9baf6f8cd" />
<img width="2507" height="1153" alt="image" src="https://github.com/user-attachments/assets/0dbbcfbf-83b4-497d-a967-44a3789fbde0" />
<img width="4" height="3" alt="image" src="https://github.com/user-attachments/assets/20441176-2de8-49cd-8907-d28f4f6f4f68" />
<img width="2499" height="1280" alt="image" src="https://github.com/user-attachments/assets/4cb9e44d-e871-4851-a69b-bf60a31508f1" />
<img width="2025" height="1307" alt="image" src="https://github.com/user-attachments/assets/cae2c728-2d6f-47e4-b352-014f06fa3e11" />

