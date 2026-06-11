<script lang="ts">
  import { createEventDispatcher, onDestroy } from 'svelte';
  import './styles/TrainPanel.css';
  import * as echarts from 'echarts';

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
    shap_available?: boolean;
  }

  interface ShapData {
    model_id: string;
    model_label: string;
    explainer_type: string;
    task: string;
    n_explained: number;
    base_value: number;
    global_importance: { feature: string; mean_abs: number; importance_pct: number }[];
    beeswarm: {
      feature: string;
      mean_abs: number;
      shap_values: number[];
      feature_norm: number[];
      feature_raw: number[];
    }[];
    waterfall: {
      base_value: number;
      final_value: number;
      bars: { feature: string; shap: number; start: number; end: number; positive: boolean }[];
      sample_index: number;
    };
    dependence: {
      feature: string;
      feature_vals: number[];
      shap_vals: number[];
      mean_abs: number;
    }[];
  }

  export let datasetId: string | null = null;
  export let datasetMeta: Dataset | null = null;
  export let apiBase = 'http://127.0.0.1:8000';

  const dispatch = createEventDispatcher();

  // ── Config state ──
  let target        = '';
  let task          = 'classification';
  let testSize      = 0.2;
  let sampleMode    = 'all';
  let sampleFixed   = 1000;
  let samplePct     = 100;
  let cvFolds       = 5;
  let scaleFeats    = true;
  let saveAs        = '';
  let selectedModels: string[] = [];

  // ── Training result ──
  let loading   = false;
  let result: TrainResult | null = null;
  let error     = '';
  let activeTab = 'config';

  // ── SHAP state ──
  let shapLoading     = false;
  let shapError       = ''
  let shapData: ShapData | null = null;
  let shapModelId     = '';
  let shapSampleSize  = 200;
  let shapMaxFeatures = 15;
  let shapSampleIdx   = 0;
  let shapChartType   = 'beeswarm'; // beeswarm | waterfall | dependence
  let shapDepFeature  = '';

  // ECharts instances
  let beeswarmContainer: HTMLDivElement | null = null;
  let waterfallContainer: HTMLDivElement | null = null;
  let dependenceContainer: HTMLDivElement | null = null;
  let beeswarmChart: echarts.ECharts | null = null;
  let waterfallChart: echarts.ECharts | null = null;
  let dependenceChart: echarts.ECharts | null = null;

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

  // Cuando cambia shapData o el tipo de gráfico, renderizar
  $: if (shapData && activeTab === 'shap') {
    setTimeout(() => renderShapChart(), 80);
  }

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
    loading = true; error = ''; result = null; shapData = null;
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
      // Preseleccionar modelo para SHAP = mejor del entrenamiento
      if (result?.best_model) shapModelId = result.best_model;
      activeTab = 'results';
      dispatch('refresh');
    } catch (e) {
      error = String(e);
    } finally {
      loading = false;
    }
  }

  async function runShap(): Promise<void> {
    if (!datasetId || !target) return;
    shapLoading = true; shapError = ''; shapData = null;
    destroyShapCharts();
    try {
      const res = await fetch(`${apiBase}/api/v1/train/${datasetId}/shap`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target,
          task,
          model_id:       shapModelId || result?.best_model || 'random_forest',
          sample_size:    shapSampleSize,
          max_features:   shapMaxFeatures,
          test_size:      testSize,
          random_state:   42,
          scale_features: scaleFeats,
          sample_index:   shapSampleIdx,
        }),
      });
      if (!res.ok) { const d = await res.json(); throw new Error(d.detail); }
      shapData = await res.json();
      // Preseleccionar feature de dependencia = la más importante
      if (shapData?.dependence?.length) {
        shapDepFeature = shapData.dependence[0].feature;
      }
      shapChartType = 'beeswarm';
      setTimeout(() => renderShapChart(), 100);
    } catch (e) {
      shapError = String(e);
    } finally {
      shapLoading = false;
    }
  }

  function destroyShapCharts(): void {
    [beeswarmChart, waterfallChart, dependenceChart].forEach(c => {
      try { c?.dispose(); } catch (_) {}
    });
    beeswarmChart = waterfallChart = dependenceChart = null;
  }

  onDestroy(destroyShapCharts);

  // Color para valores SHAP positivos/negativos y feature_norm
  function shapColor(norm: number): string {
    // norm: 0 = bajo valor feature (azul), 1 = alto (rojo)
    const r = Math.round(norm * 220 + (1 - norm) * 52);
    const g = Math.round(norm * 50  + (1 - norm) * 152);
    const b = Math.round(norm * 50  + (1 - norm) * 235);
    return `rgb(${r},${g},${b})`;
  }

  function renderShapChart(): void {
    if (!shapData) return;

    if (shapChartType === 'beeswarm') renderBeeswarm();
    else if (shapChartType === 'waterfall') renderWaterfall();
    else if (shapChartType === 'dependence') renderDependence();
  }

  function renderBeeswarm(): void {
    if (!beeswarmContainer || !shapData) return;
    if (beeswarmChart) beeswarmChart.dispose();
    beeswarmChart = echarts.init(beeswarmContainer);

    const features = [...shapData.beeswarm].reverse(); // menor importancia abajo
    const seriesData: any[] = [];

    features.forEach((feat, yIdx) => {
      feat.shap_values.forEach((sv, i) => {
        seriesData.push({
          value: [sv, yIdx],
          itemStyle: { color: shapColor(feat.feature_norm[i]) },
        });
      });
    });

    beeswarmChart.setOption({
      backgroundColor: 'transparent',
      tooltip: {
        trigger: 'item',
        formatter: (p: any) => {
          const feat = features[p.value[1]];
          const i    = feat.shap_values.indexOf(p.value[0]);
          return `<b>${feat.feature}</b><br/>SHAP: ${p.value[0].toFixed(4)}<br/>Valor: ${feat.feature_raw[i]?.toFixed(3) ?? '?'}`;
        },
      },
      grid: { top: 20, bottom: 50, left: 180, right: 80 },
      xAxis: {
        type: 'value',
        name: 'Valor SHAP',
        nameLocation: 'middle',
        nameGap: 32,
        axisLine: { lineStyle: { color: '#94a3b8' } },
        axisLabel: { color: '#64748b', fontSize: 11 },
        splitLine: { lineStyle: { color: '#f1f5f9' } },
      },
      yAxis: {
        type: 'category',
        data: features.map(f => f.feature),
        axisLabel: {
          color: '#334155',
          fontSize: 11,
          width: 160,
          overflow: 'truncate',
        },
        axisLine: { show: false },
        axisTick: { show: false },
      },
      series: [{
        type: 'scatter',
        data: seriesData,
        symbolSize: 5,
        opacity: 0.75,
      }],
      visualMap: {
        show: true,
        type: 'continuous',
        min: 0,
        max: 1,
        text: ['Alto', 'Bajo'],
        orient: 'vertical',
        right: 10,
        top: 'center',
        itemHeight: 120,
        textStyle: { fontSize: 10, color: '#64748b' },
        inRange: {
          color: ['#3498db', '#e74c3c'],
        },
        dimension: 0,
        seriesIndex: 0,
        calculable: false,
      },
    });
  }

  function renderWaterfall(): void {
    if (!waterfallContainer || !shapData) return;
    if (waterfallChart) waterfallChart.dispose();
    waterfallChart = echarts.init(waterfallContainer);

    const bars = shapData.waterfall.bars;
    const labels = bars.map(b => b.feature);
    const base   = shapData.waterfall.base_value;

    // Datos para gráfico de cascada horizontal
    const positiveData: (number | null)[] = bars.map(b => b.positive ? b.shap : null);
    const negativeData: (number | null)[] = bars.map(b => !b.positive ? b.shap : null);

    // Invisible offset para posicionar barras
    const offsetData: number[] = bars.map(b => b.positive ? b.start : b.end);

    waterfallChart.setOption({
      backgroundColor: 'transparent',
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: (params: any[]) => {
          const b = bars[params[0].dataIndex];
          const sign = b.shap >= 0 ? '+' : '';
          return `<b>${b.feature}</b><br/>SHAP: ${sign}${b.shap.toFixed(4)}<br/>Valor acumulado: ${b.end.toFixed(4)}`;
        },
      },
      grid: { top: 20, bottom: 50, left: 220, right: 30 },
      xAxis: {
        type: 'value',
        name: 'Valor SHAP acumulado',
        nameLocation: 'middle',
        nameGap: 32,
        axisLabel: { color: '#64748b', fontSize: 11 },
        splitLine: { lineStyle: { color: '#f1f5f9' } },
      },
      yAxis: {
        type: 'category',
        data: labels,
        inverse: false,
        axisLabel: {
          color: '#334155',
          fontSize: 11,
          width: 200,
          overflow: 'truncate',
        },
        axisLine: { show: false },
        axisTick: { show: false },
      },
      series: [
        // Offset invisible
        {
          type: 'bar',
          stack: 'total',
          data: offsetData,
          itemStyle: { color: 'transparent' },
          emphasis: { disabled: true },
        },
        // Barras positivas
        {
          name: 'Positivo',
          type: 'bar',
          stack: 'total',
          data: bars.map(b => b.positive ? b.shap : 0),
          itemStyle: {
            color: '#e74c3c',
            borderRadius: [0, 4, 4, 0],
          },
          label: {
            show: true,
            position: 'right',
            formatter: (p: any) => {
              const v = bars[p.dataIndex].shap;
              return v !== 0 ? `+${v.toFixed(3)}` : '';
            },
            fontSize: 10,
            color: '#e74c3c',
          },
        },
        // Barras negativas
        {
          name: 'Negativo',
          type: 'bar',
          stack: 'total',
          data: bars.map(b => !b.positive ? b.shap : 0),
          itemStyle: {
            color: '#3498db',
            borderRadius: [4, 0, 0, 4],
          },
          label: {
            show: true,
            position: 'left',
            formatter: (p: any) => {
              const v = bars[p.dataIndex].shap;
              return v !== 0 ? v.toFixed(3) : '';
            },
            fontSize: 10,
            color: '#3498db',
          },
        },
      ],
      graphic: [
        {
          type: 'line',
          shape: { x1: 0, y1: 0, x2: 0, y2: '100%' },
          style: { stroke: '#94a3b8', lineWidth: 1, lineDash: [4, 4] },
        },
      ],
    });
  }

  function renderDependence(): void {
    if (!dependenceContainer || !shapData || !shapDepFeature) return;
    if (dependenceChart) dependenceChart.dispose();
    dependenceChart = echarts.init(dependenceContainer);

    const feat = shapData.dependence.find(d => d.feature === shapDepFeature);
    if (!feat) return;

    const data = feat.feature_vals.map((fv, i) => [fv, feat.shap_vals[i]]);

    dependenceChart.setOption({
      backgroundColor: 'transparent',
      tooltip: {
        trigger: 'item',
        formatter: (p: any) => `<b>${shapDepFeature}</b><br/>Valor: ${p.value[0].toFixed(4)}<br/>SHAP: ${p.value[1].toFixed(4)}`,
      },
      grid: { top: 20, bottom: 55, left: 70, right: 30 },
      xAxis: {
        type: 'value',
        name: shapDepFeature,
        nameLocation: 'middle',
        nameGap: 36,
        axisLabel: { color: '#64748b', fontSize: 11 },
        splitLine: { lineStyle: { color: '#f1f5f9' } },
      },
      yAxis: {
        type: 'value',
        name: 'Valor SHAP',
        nameLocation: 'middle',
        nameGap: 50,
        axisLabel: { color: '#64748b', fontSize: 11 },
        splitLine: { lineStyle: { color: '#f1f5f9' } },
        axisLine: { lineStyle: { color: '#94a3b8' } },
      },
      series: [{
        type: 'scatter',
        data,
        symbolSize: 6,
        itemStyle: { color: '#5b21b6', opacity: 0.65 },
      }],
    });
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

  // Re-renderizar SHAP si cambia tipo o feature de dependencia
  $: if (shapData && activeTab === 'shap' && shapChartType) {
    setTimeout(() => {
      destroyShapCharts();
      renderShapChart();
    }, 60);
  }
</script>

<div class="train-panel">
  {#if !datasetId}
    <div class="empty-state">
      <p>Selecciona un dataset para entrenar modelos ML.</p>
    </div>

  {:else}
    <!-- ── Tabs ── -->
    <div class="tab-bar">
      {#each [
        { id: 'config',    label: 'Configuracion',  disabled: false },
        { id: 'results',   label: 'Comparacion',    disabled: !result },
        { id: 'features',  label: 'Features',       disabled: !result },
        { id: 'confusion', label: 'Confusion',      disabled: !result || result.task !== 'classification' },
        { id: 'shap',      label: 'SHAP',           disabled: false },
      ] as tab}
        <button
          class="tab-btn"
          class:tab-active={activeTab === tab.id}
          disabled={tab.disabled}
          on:click={() => { if (!tab.disabled) activeTab = tab.id; }}
        >{tab.label}</button>
      {/each}
    </div>

    <!-- ══════════════ TAB CONFIG ══════════════ -->
    {#if activeTab === 'config'}
      <div class="scroll-area">
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

        <div class="card">
          <p class="card-title">Tamano de muestra</p>
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
                <input id="sample-pct" type="range" class="slider" min="5" max="100" step="5" bind:value={samplePct} />
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

        <div class="card">
          <p class="card-title">Hiperparametros generales</p>
          <div class="grid-3">
            <div class="field">
              <label class="field-label" for="test-size">
                Proporcion de test: {(testSize * 100).toFixed(0)}%
              </label>
              <input id="test-size" type="range" class="slider" min="0.1" max="0.4" step="0.05" bind:value={testSize} />
            </div>
            <div class="field">
              <label class="field-label" for="cv-folds">Folds de validacion cruzada</label>
              <input id="cv-folds" type="number" class="input" bind:value={cvFolds} min="2" max="10" />
            </div>
            <div class="field" style="align-self:flex-end;">
              <label class="check-label">
                <input type="checkbox" bind:checked={scaleFeats} />
                Escalar features (StandardScaler)
              </label>
            </div>
          </div>
        </div>

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

        <div class="card">
          <p class="card-title">Guardar predicciones (opcional)</p>
          <input class="input" bind:value={saveAs} placeholder="Nombre del dataset de predicciones" />
        </div>

        <button class="run-btn" on:click={runTraining}
          disabled={loading || !target || selectedModels.length === 0}>
          {loading ? 'Entrenando...' : 'Entrenar modelos'}
        </button>

        {#if loading}
          <div class="loading-hint">Esto puede tomar entre 5 y 60 segundos...</div>
        {/if}

        {#if error}
          <div class="alert-error">{error}</div>
        {/if}
      </div>

    <!-- ══════════════ TAB RESULTADOS ══════════════ -->
    {:else if activeTab === 'results' && result}
      <div class="scroll-area">
        <div class="kpi-row">
          {#each [
            { l: 'Filas usadas',  v: (result.n_samples_total ?? 0).toLocaleString() },
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

    <!-- ══════════════ TAB FEATURES ══════════════ -->
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
          <p class="muted-text">Este modelo no provee importancia de features.</p>
        {/if}
      </div>

    <!-- ══════════════ TAB CONFUSION ══════════════ -->
    {:else if activeTab === 'confusion' && result}
      <div class="scroll-area">
        {#if result.models[result.best_model]?.confusion_matrix}
          {@const cm  = result.models[result.best_model]?.confusion_matrix ?? []}
          {@const cls = result.classes}
          <p class="section-h4">Matriz de confusion — {result.models[result.best_model]?.label}</p>
          <p class="card-desc">Filas = clase real. Columnas = clase predicha.</p>
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
          <p class="muted-text">No hay matriz de confusion disponible.</p>
        {/if}
      </div>

    <!-- ══════════════ TAB SHAP ══════════════ -->
    {:else if activeTab === 'shap'}
      <div class="scroll-area">
        <!-- ── Panel de configuración SHAP ── -->
        <div class="card shap-config-card">
          <p class="card-title">Explicabilidad SHAP</p>
          <p class="card-desc">
            SHAP (SHapley Additive exPlanations) cuantifica la contribucion de cada feature
            a la prediccion del modelo. Los valores SHAP positivos empujan la prediccion hacia
            arriba; los negativos la reducen.
          </p>

          <div class="shap-config-grid">
            <div class="field">
              <label class="field-label" for="shap-target">Variable objetivo</label>
              <select id="shap-target" class="select" bind:value={target}>
                {#each cols as col}<option value={col}>{col}</option>{/each}
              </select>
            </div>
            <div class="field">
              <label class="field-label" for="shap-task">Tarea</label>
              <select id="shap-task" class="select" bind:value={task}>
                <option value="classification">Clasificacion</option>
                <option value="regression">Regresion</option>
              </select>
            </div>
            <div class="field">
              <label class="field-label" for="shap-model">Modelo</label>
              <select id="shap-model" class="select" bind:value={shapModelId}>
                {#each Object.entries(modelMap) as [id, lbl]}
                  <option value={id}>{lbl}</option>
                {/each}
              </select>
            </div>
            <div class="field">
              <label class="field-label" for="shap-samples">
                Muestras a explicar: {shapSampleSize}
              </label>
              <input id="shap-samples" type="range" class="slider"
                min="50" max="500" step="50" bind:value={shapSampleSize} />
            </div>
            <div class="field">
              <label class="field-label" for="shap-features">
                Top features: {shapMaxFeatures}
              </label>
              <input id="shap-features" type="range" class="slider"
                min="5" max="30" step="1" bind:value={shapMaxFeatures} />
            </div>
            <div class="field" style="align-self:flex-end;">
              <button class="run-btn shap-run-btn"
                on:click={runShap}
                disabled={shapLoading || !target}>
                {shapLoading ? 'Calculando SHAP...' : 'Calcular SHAP'}
              </button>
            </div>
          </div>

          {#if !result}
            <div class="shap-notice">
              No se necesita entrenar antes: SHAP entrena el modelo internamente.
              Para comparar modelos primero, usa el tab "Configuracion".
            </div>
          {/if}
        </div>

        {#if shapLoading}
          <div class="shap-loading">
            <div class="shap-spinner"></div>
            <span>Calculando valores SHAP para {shapSampleSize} muestras...</span>
          </div>
        {/if}

        {#if shapError}
          <div class="alert-error">{shapError}</div>
        {/if}

        {#if shapData}
          <!-- ── Encabezado de resultados ── -->
          <div class="shap-result-header">
            <div class="shap-meta-pills">
              <span class="shap-pill shap-pill-model">{shapData.model_label}</span>
              <span class="shap-pill shap-pill-explainer">{shapData.explainer_type}Explainer</span>
              <span class="shap-pill shap-pill-n">{shapData.n_explained} muestras</span>
              <span class="shap-pill shap-pill-base">
                Valor base: {shapData.base_value.toFixed(3)}
              </span>
            </div>
          </div>

          <!-- ── Ranking global de importancia ── -->
          <div class="card shap-importance-card">
            <p class="card-title">Importancia global por |SHAP| medio</p>
            <p class="card-desc">
              Promedio del valor absoluto de los valores SHAP sobre todas las muestras.
              Mide cuanto mueve en promedio cada feature la prediccion del modelo.
            </p>
            <div class="shap-importance-list">
              {#each shapData.global_importance as feat, i}
                {@const maxVal = shapData.global_importance[0].mean_abs}
                <div class="shap-imp-row">
                  <span class="shap-imp-rank">{i + 1}</span>
                  <span class="shap-imp-name" title={feat.feature}>{feat.feature}</span>
                  <div class="shap-imp-bar-wrap">
                    <div class="shap-imp-bar"
                      style="width:{(feat.mean_abs / maxVal * 100).toFixed(1)}%;
                             background: {i < 3 ? '#7c3aed' : i < 7 ? '#1d4ed8' : '#64748b'}">
                    </div>
                  </div>
                  <span class="shap-imp-val">{feat.mean_abs.toFixed(4)}</span>
                  <span class="shap-imp-pct">{feat.importance_pct.toFixed(1)}%</span>
                </div>
              {/each}
            </div>
          </div>

          <!-- ── Selector de tipo de gráfico ── -->
          <div class="shap-chart-tabs">
            {#each [
              { id: 'beeswarm',   label: 'Beeswarm',     desc: 'Distribucion SHAP por feature' },
              { id: 'waterfall',  label: 'Waterfall',    desc: 'Contribucion por observacion'  },
              { id: 'dependence', label: 'Dependencia',  desc: 'Valor feature vs SHAP'          },
            ] as ct}
              <button
                class="shap-chart-tab"
                class:shap-chart-tab-active={shapChartType === ct.id}
                on:click={() => shapChartType = ct.id}
              >
                <span class="sct-label">{ct.label}</span>
                <span class="sct-desc">{ct.desc}</span>
              </button>
            {/each}
          </div>

          <!-- ── Beeswarm ── -->
          {#if shapChartType === 'beeswarm'}
            <div class="card shap-chart-card">
              <p class="card-title">SHAP Summary Plot (Beeswarm)</p>
              <p class="card-desc">
                Cada punto es una observacion. La posicion en X indica la magnitud del valor SHAP
                (efecto sobre la prediccion). El color codifica el valor de la feature:
                <span style="color:#e74c3c;font-weight:600;">rojo = valor alto</span>,
                <span style="color:#3498db;font-weight:600;">azul = valor bajo</span>.
              </p>
              <div class="shap-color-legend">
                <span style="font-size:11px;color:#64748b;">Valor de feature:</span>
                <div class="shap-color-gradient"></div>
                <span style="font-size:10px;color:#3498db;">Bajo</span>
                <span style="font-size:10px;color:#e74c3c;">Alto</span>
              </div>
              <div
                bind:this={beeswarmContainer}
                style="height:{Math.max(300, shapData.beeswarm.length * 28 + 80)}px; width:100%;">
              </div>
            </div>

          <!-- ── Waterfall ── -->
          {:else if shapChartType === 'waterfall'}
            <div class="card shap-chart-card">
              <p class="card-title">SHAP Waterfall Plot</p>
              <p class="card-desc">
                Muestra como cada feature empuja la prediccion desde el valor base
                ({shapData.waterfall.base_value.toFixed(3)})
                hasta el valor final ({shapData.waterfall.final_value.toFixed(3)}).
                <span style="color:#e74c3c;font-weight:600;">Rojo = empuja hacia arriba</span>,
                <span style="color:#3498db;font-weight:600;">azul = empuja hacia abajo</span>.
              </p>
              <div class="shap-waterfall-meta">
                <label class="field-label" for="shap-sample-idx" style="margin-right:8px;">
                  Observacion a analizar:
                </label>
                <input id="shap-sample-idx" type="number" class="input"
                  style="width:90px; display:inline-block;"
                  bind:value={shapSampleIdx}
                  min="0"
                  max={shapData.n_explained - 1}
                  on:change={() => {
                    if (shapData) {
                      runShap();
                    }
                  }}
                />
                <span style="font-size:11px;color:#94a3b8;margin-left:6px;">
                  / {shapData.n_explained - 1} disponibles
                </span>
              </div>
              <div
                bind:this={waterfallContainer}
                style="height:{Math.max(300, shapData.waterfall.bars.length * 34 + 100)}px; width:100%;">
              </div>
            </div>

          <!-- ── Dependencia ── -->
          {:else if shapChartType === 'dependence'}
            <div class="card shap-chart-card">
              <p class="card-title">SHAP Dependence Plot</p>
              <p class="card-desc">
                Relacion entre el valor de una feature y su valor SHAP.
                Revela efectos no lineales e interacciones del modelo.
              </p>
              <div class="shap-dep-selector">
                <label class="field-label" for="dep-feature">Feature a explorar:</label>
                <select id="dep-feature" class="select" style="max-width:280px;"
                  bind:value={shapDepFeature}
                  on:change={() => setTimeout(() => { destroyShapCharts(); renderShapChart(); }, 60)}>
                  {#each shapData.dependence as feat}
                    <option value={feat.feature}>
                      {feat.feature} (|SHAP| medio: {feat.mean_abs.toFixed(4)})
                    </option>
                  {/each}
                </select>
              </div>
              <div
                bind:this={dependenceContainer}
                style="height:360px; width:100%;">
              </div>
            </div>
          {/if}

          <!-- ── Guía de interpretación ── -->
          <div class="card shap-guide-card">
            <p class="card-title">Como interpretar los resultados SHAP</p>
            <div class="shap-guide-grid">
              <div class="shap-guide-item">
                <span class="shap-guide-icon shap-guide-icon-beeswarm"></span>
                <div>
                  <p class="shap-guide-title">Beeswarm</p>
                  <p class="shap-guide-text">
                    Features en la parte superior tienen mayor impacto global.
                    Puntos dispersos a la derecha/izquierda indican efectos consistentes.
                    Puntos agrupados en el centro indican baja influencia.
                  </p>
                </div>
              </div>
              <div class="shap-guide-item">
                <span class="shap-guide-icon shap-guide-icon-waterfall"></span>
                <div>
                  <p class="shap-guide-title">Waterfall</p>
                  <p class="shap-guide-text">
                    Cada barra muestra la contribucion de una feature a la prediccion
                    para una observacion especifica. Util para auditar predicciones
                    individuales o detectar casos anomalos.
                  </p>
                </div>
              </div>
              <div class="shap-guide-item">
                <span class="shap-guide-icon shap-guide-icon-dep"></span>
                <div>
                  <p class="shap-guide-title">Dependencia</p>
                  <p class="shap-guide-text">
                    Una linea horizontal indica efecto lineal.
                    Una curva indica efecto no lineal. Patrones en forma de U o S
                    revelan umbrales o saturaciones en el modelo.
                  </p>
                </div>
              </div>
            </div>
          </div>
        {/if}
      </div>
    {/if}
  {/if}
</div>

