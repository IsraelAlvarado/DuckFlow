<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import './styles/TrainPanel.css';

  interface Dataset {
    id: string;
    name: string;
    total_rows: number;
    columns: string[];
    numeric_columns: string[];
    categorical_columns: string[];
  }

  interface ModelResult {
    label: string;
    error?: string;
    accuracy?: number;
    f1?: number;
    precision?: number;
    recall?: number;
    roc_auc?: number;
    r2?: number;
    mae?: number;
    rmse?: number;
    mape?: number;
    cv_mean?: number;
    cv_std?: number;
    confusion_matrix?: number[][];
    feature_importances?: { feature: string; importance: number; importance_pct: number }[];
  }

  interface TrainResult {
    task: string;
    target: string;
    n_samples_used: number;
    n_samples_total: number;
    n_features: number;
    feature_names: string[];
    best_model: string;
    best_score: number;
    primary_metric: string;
    classes: string[];
    cv_folds: number;
    ranking: any[];
    models: Record<string, ModelResult>;
    predictions_dataset_id?: string;
  }

  export let datasetId: string | null = null;
  export let datasetMeta: Dataset | null = null;
  export let apiBase = 'http://127.0.0.1:8000';

  const dispatch = createEventDispatcher();

  let target        = '';
  let task          = 'classification';
  let testSize      = 0.2;
  let sampleMode    = 'all';   // all | fixed | pct
  let sampleFixed   = 1000;
  let samplePct     = 100;
  let cvFolds       = 5;
  let scaleFeats    = true;
  let saveAs        = '';
  let selectedModels: string[] = [];

  let loading   = false;
  let result: TrainResult | null = null;
  let error     = '';
  let activeTab = 'config';   // config | results | features | confusion

  const CLASSIFICATION_MODELS: Record<string, string> = {
    logistic_regression: 'Regresion Logistica',
    random_forest:       'Random Forest',
    gradient_boosting:   'Gradient Boosting',
    decision_tree:       'Arbol de Decision',
    knn:                 'K-Nearest Neighbors',
    svm:                 'SVM',
  };

  const REGRESSION_MODELS: Record<string, string> = {
    linear_regression: 'Regresion Lineal',
    ridge:             'Ridge',
    lasso:             'Lasso',
    random_forest:     'Random Forest',
    gradient_boosting: 'Gradient Boosting',
    decision_tree:     'Arbol de Decision',
  };

  $: cols     = datasetMeta?.columns ?? [];
  $: modelMap = task === 'classification' ? CLASSIFICATION_MODELS : REGRESSION_MODELS;

  $: if (!target && cols.length) target = cols[cols.length - 1];
  $: if (selectedModels.length === 0 && Object.keys(modelMap).length)
       selectedModels = Object.keys(modelMap);

  $: effectiveSample = (() => {
    const total = datasetMeta?.total_rows ?? 0;
    if (sampleMode === 'all')   return total;
    if (sampleMode === 'fixed') return Math.min(sampleFixed, total);
    return Math.round(total * samplePct / 100);
  })();

  function toggleModel(id: string): void {
    selectedModels = selectedModels.includes(id)
      ? selectedModels.filter(m => m !== id)
      : [...selectedModels, id];
  }

  function selectAllModels(): void {
    selectedModels = selectedModels.length === Object.keys(modelMap).length
      ? [] : Object.keys(modelMap);
  }

  function getSampleSize(): number | null {
    const total = datasetMeta?.total_rows ?? 0;
    if (sampleMode === 'all')   return null;
    if (sampleMode === 'fixed') return Math.min(sampleFixed, total);
    return Math.max(10, Math.round(total * samplePct / 100));
  }

  async function runTraining(): Promise<void> {
    if (!datasetId || !target) return;
    loading = true; error = ''; result = null;
    try {
      const res = await fetch(`${apiBase}/api/v1/train/${datasetId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target,
          task,
          test_size:      testSize,
          sample_size:    getSampleSize(),
          cv_folds:       cvFolds,
          scale_features: scaleFeats,
          models:         selectedModels.length > 0 ? selectedModels : null,
          save_as:        saveAs || undefined,
        }),
      });
      if (!res.ok) { const d = await res.json(); throw new Error(d.detail); }
      result = await res.json();
      activeTab = 'results';
      dispatch('refresh');
    } catch (e) {
      error = String(e);
    } finally {
      loading = false;
    }
  }

  const METRIC_LABELS: Record<string, string> = {
    accuracy: 'Accuracy', f1: 'F1 (pond.)', precision: 'Precision',
    recall: 'Recall', roc_auc: 'ROC-AUC',
    r2: 'R²', mae: 'MAE', rmse: 'RMSE', mape: 'MAPE (%)',
    cv_mean: 'CV Media',
  };

  function scoreColor(key: string, val: number | undefined | null): string {
    if (val == null) return '#94a3b8';
    if (['mae', 'rmse', 'mape'].includes(key))
      return val < 10 ? '#10b981' : val < 30 ? '#f59e0b' : '#ef4444';
    return val >= 0.85 ? '#10b981' : val >= 0.70 ? '#f59e0b' : '#ef4444';
  }

  function fmt(v: number | undefined | null, decimals = 4): string {
    if (v == null) return '—';
    return typeof v === 'number' ? v.toFixed(decimals) : String(v);
  }

  function fmtPct(v: number | undefined | null): string {
    if (v == null) return '—';
    return (v * 100).toFixed(2) + '%';
  }

  const CLASS_METRICS = ['accuracy', 'f1', 'precision', 'recall', 'roc_auc', 'cv_mean'];
  const REG_METRICS   = ['r2', 'mae', 'rmse', 'mape', 'cv_mean'];

  $: activeMetrics = result?.task === 'classification' ? CLASS_METRICS : REG_METRICS;
</script>

<div class="train-panel">
  {#if !datasetId}
    <div class="empty-state">
      <p>Selecciona un dataset para entrenar modelos ML.</p>
    </div>

  {:else}
    <!-- ── Tabs internos ── -->
    <div class="tab-bar">
      {#each [
        { id: 'config',    label: 'Configuracion' },
        { id: 'results',   label: 'Comparacion',  disabled: !result },
        { id: 'features',  label: 'Features',     disabled: !result },
        { id: 'confusion', label: 'Confusion',    disabled: !result || result.task !== 'classification' },
      ] as tab}
        <button
          class="tab-btn"
          class:tab-active={activeTab === tab.id}
          disabled={tab.disabled}
          on:click={() => { if (!tab.disabled) activeTab = tab.id; }}
        >{tab.label}</button>
      {/each}
    </div>

    <!-- ════════════════════════════════ TAB CONFIG ════════════════════ -->
    {#if activeTab === 'config'}
      <div class="scroll-area">

        <!-- Target y tarea -->
        <div class="card">
          <p class="card-title">Datos de entrenamiento</p>
          <p class="card-desc">{datasetMeta?.name} — {datasetMeta?.total_rows?.toLocaleString()} filas totales</p>
          <div class="grid-2">
            <div class="field">
              <label class="field-label" for="target-col">Columna objetivo (target)</label>
              <select id="target-col" class="select" bind:value={target}>
                {#each cols as col}<option value={col}>{col}</option>{/each}
              </select>
            </div>
            <div class="field">
              <label class="field-label" for="task-sel">Tipo de tarea</label>
              <select id="task-sel" class="select" bind:value={task}>
                <option value="classification">Clasificacion</option>
                <option value="regression">Regresion</option>
              </select>
            </div>
          </div>
        </div>

        <!-- Tamaño de muestra -->
        <div class="card">
          <p class="card-title">Tamano de muestra</p>
          <p class="card-desc">Controla cuantas filas se usan para entrenar. Util con datasets grandes.</p>

          <div class="mode-row">
            {#each [['all','Todas las filas'],['fixed','Cantidad fija'],['pct','Porcentaje']] as [val, lbl]}
              <label class="radio-label">
                <input type="radio" name="sampleMode" value={val} bind:group={sampleMode} />
                {lbl}
              </label>
            {/each}
          </div>

          {#if sampleMode === 'fixed'}
            <div class="field" style="max-width:260px; margin-top:10px;">
              <label class="field-label" for="sample-fixed">Numero de filas</label>
              <input id="sample-fixed" type="number" class="input"
                bind:value={sampleFixed}
                min="10" max={datasetMeta?.total_rows ?? 1000000} step="100" />
            </div>

          {:else if sampleMode === 'pct'}
            <div class="field" style="max-width:260px; margin-top:10px;">
              <label class="field-label" for="sample-pct">Porcentaje (%)</label>
              <div class="slider-row">
                <input id="sample-pct" type="range" class="slider"
                  min="5" max="100" step="5" bind:value={samplePct} />
                <span class="slider-val">{samplePct}%</span>
              </div>
            </div>
          {/if}

          <div class="sample-summary">
            <span class="sample-pill">
              Filas efectivas: <strong>{effectiveSample.toLocaleString()}</strong>
              de {datasetMeta?.total_rows?.toLocaleString()}
            </span>
            {#if sampleMode !== 'all' && effectiveSample < 100}
              <span class="warn-chip">Muestra muy pequena (menos de 100 filas)</span>
            {/if}
          </div>
        </div>

        <!-- Hiperparámetros -->
        <div class="card">
          <p class="card-title">Hiperparametros generales</p>
          <div class="grid-3">
            <div class="field">
              <label class="field-label" for="test-size">
                Proporcion de test: {(testSize * 100).toFixed(0)}%
              </label>
              <input id="test-size" type="range" class="slider"
                min="0.1" max="0.4" step="0.05" bind:value={testSize} />
            </div>
            <div class="field">
              <label class="field-label" for="cv-folds">Folds de validacion cruzada</label>
              <input id="cv-folds" type="number" class="input"
                bind:value={cvFolds} min="2" max="10" />
            </div>
            <div class="field" style="align-self:flex-end;">
              <label class="check-label">
                <input type="checkbox" bind:checked={scaleFeats} />
                Escalar features (StandardScaler)
              </label>
            </div>
          </div>
        </div>

        <!-- Modelos -->
        <div class="card">
          <div class="card-header-row">
            <p class="card-title">Modelos a entrenar</p>
            <button class="tiny-btn" on:click={selectAllModels}>
              {selectedModels.length === Object.keys(modelMap).length ? 'Ninguno' : 'Todos'}
            </button>
          </div>
          <div class="model-grid">
            {#each Object.entries(modelMap) as [id, lbl]}
              <label class="model-card" class:model-card-active={selectedModels.includes(id)}>
                <input type="checkbox"
                  checked={selectedModels.includes(id)}
                  on:change={() => toggleModel(id)} />
                <span class="model-name">{lbl}</span>
              </label>
            {/each}
          </div>
          {#if selectedModels.length === 0}
            <p class="warn-text">Selecciona al menos un modelo.</p>
          {/if}
        </div>

        <!-- Guardar predicciones -->
        <div class="card">
          <p class="card-title">Guardar predicciones (opcional)</p>
          <p class="card-desc">El mejor modelo generara un dataset con la columna "prediction" agregada.</p>
          <input class="input" bind:value={saveAs}
            placeholder="Nombre del dataset de predicciones" />
        </div>

        <!-- Botón -->
        <button class="run-btn"
          on:click={runTraining}
          disabled={loading || !target || selectedModels.length === 0}>
          {loading ? 'Entrenando...' : 'Entrenar modelos'}
        </button>

        {#if loading}
          <div class="loading-hint">
            Esto puede tomar entre 5 y 60 segundos segun el tamano de la muestra y el numero de modelos.
          </div>
        {/if}

        {#if error}
          <div class="alert-error">{error}</div>
        {/if}
      </div>

    <!-- ════════════════════════════════ TAB RESULTADOS ══════════════ -->
    {:else if activeTab === 'results' && result}
      <div class="scroll-area">
        <div class="kpi-row">
          {#each [
            { l: 'Filas usadas',  v: result.n_samples_used.toLocaleString() },
            { l: 'Features',      v: result.n_features },
            { l: 'Folds CV',      v: result.cv_folds },
            { l: 'Mejor modelo',  v: result.models[result.best_model]?.label ?? result.best_model },
            { l: result.primary_metric.toUpperCase(), v: fmt(result.best_score) },
          ] as k}
            <div class="kpi">
              <div class="kpi-val">{k.v}</div>
              <div class="kpi-label">{k.l}</div>
            </div>
          {/each}
        </div>

        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>Modelo</th>
                {#each activeMetrics as m}
                  <th>{METRIC_LABELS[m] ?? m}</th>
                {/each}
              </tr>
            </thead>
            <tbody>
              {#each result.ranking as row}
                <tr class:row-best={row.model === result.best_model}>
                  <td class="td-model">
                    {row.label}
                    {#if row.model === result.best_model}
                      <span class="best-badge">Mejor</span>
                    {/if}
                  </td>
                  {#each activeMetrics as m}
                    <td class="td-metric" style="color:{scoreColor(m, row[m])}">
                      {['mae','rmse','mape'].includes(m) ? fmt(row[m], 2) : fmtPct(row[m])}
                    </td>
                  {/each}
                </tr>
              {/each}
              {#each Object.entries(result.models).filter(([,m]) => m.error) as [, m]}
                <tr class="row-error">
                  <td colspan="99">{m.label}: {m.error}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>

        {#if result.predictions_dataset_id}
          <div class="success-box">
            Predicciones guardadas como nuevo dataset.
            <button class="link-btn"
              on:click={() => dispatch('selectDataset', { id: result!.predictions_dataset_id })}>
              Ver dataset
            </button>
          </div>
        {/if}
      </div>

    <!-- ════════════════════════════════ TAB FEATURES ════════════════ -->
    {:else if activeTab === 'features' && result}
      <div class="scroll-area">
        {#if result.models[result.best_model]?.feature_importances?.length}
          <p class="section-h4">
            Importancia de features — {result.models[result.best_model]?.label}
          </p>
          <div class="feat-list">
            {#each (result.models[result.best_model]?.feature_importances ?? []) as fi}
              <div class="feat-row">
                <span class="feat-name" title={fi.feature}>{fi.feature}</span>
                <div class="feat-bar-wrap">
                  <div class="feat-bar" style="width:{fi.importance_pct}%"></div>
                </div>
                <span class="feat-pct">{fi.importance_pct.toFixed(1)}%</span>
              </div>
            {/each}
          </div>
        {:else}
          <p class="muted-text">
            Este modelo no provee importancia de features (SVM, KNN).
            Usa Random Forest o Gradient Boosting para verla.
          </p>
        {/if}
      </div>

    <!-- ════════════════════════════════ TAB CONFUSION ═══════════════ -->
    {:else if activeTab === 'confusion' && result}
      <div class="scroll-area">
        {#if result.models[result.best_model]?.confusion_matrix}
          {@const cm  = result.models[result.best_model]?.confusion_matrix ?? []}
          {@const cls = result.classes}
          <p class="section-h4">
            Matriz de confusion — {result.models[result.best_model]?.label}
          </p>
          <p class="card-desc">Filas = clase real. Columnas = clase predicha. La diagonal son aciertos.</p>
          <div style="overflow-x:auto;">
            <table class="cm-table">
              <thead>
                <tr>
                  <th class="cm-corner">Real \ Pred</th>
                  {#each cls as c}<th class="cm-head">{c}</th>{/each}
                </tr>
              </thead>
              <tbody>
                {#each cm as row, i}
                  {@const rowSum = row.reduce((a, b) => a + b, 0)}
                  <tr>
                    <td class="cm-label">{cls[i] ?? i}</td>
                    {#each row as cell, j}
                      {@const pct = rowSum > 0 ? cell / rowSum : 0}
                      <td class="cm-cell"
                        class:cm-diagonal={i === j}
                        style="background:rgba(59,130,246,{pct * 0.75 + 0.05}); color:{pct > 0.5 ? 'white' : '#1e293b'};">
                        {cell}
                        <span class="cm-pct">{(pct * 100).toFixed(0)}%</span>
                      </td>
                    {/each}
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {:else}
          <p class="muted-text">No hay matriz de confusion disponible para este modelo.</p>
        {/if}
      </div>
    {/if}
  {/if}
</div>