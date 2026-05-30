<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import './styles/TransformPanel.css';

  interface DatasetMeta {
    id: string;
    name: string;
    columns: string[];
    numeric_columns: string[];
    categorical_columns: string[];
  }

  interface TransformResult {
    id: string;
    total_rows: number;
    total_features: number;
  }

  export let datasetId: string | null = null;
  export let datasetMeta: DatasetMeta | null = null;
  export let datasets: any[] = [];
  export let apiBase = 'http://127.0.0.1:8000';

  const dispatch = createEventDispatcher();

  let loading = false;
  let result: TransformResult | null = null;
  let error = '';
  let log: string[] = [];
  let saveAsName = '';
  let overwrite = false;

  let operation = 'scale';

  let scaleMethod = 'minmax';
  let scaleCols: string[] = [];

  let encodeCol = '';
  let encodeMethod = 'onehot';

  let groupbyCols: string[] = [];
  let groupbyAggCol = '';
  let groupbyAggFn = 'sum';

  let binCol = '';
  let binCount = 5;
  let binMethod = 'cut';

  let dateFeatCol = '';
  let dateFeats: string[] = ['year', 'month', 'day', 'dayofweek'];

  let logCols: string[] = [];
  let logBase = 'e';

  let rollingCol = '';
  let rollingWindow = 7;
  let rollingAgg = 'mean';

  let lagCol = '';
  let lagPeriods = 1;

  let concatIds: string[] = [];
  let concatAxis = 0;

  let outlierCol = '';
  let outlierMethod = 'iqr';
  let outlierThreshold = 1.5;

  let pivotIndex = '';
  let pivotColumns = '';
  let pivotValues = '';
  let pivotAgg = 'mean';

  $: cols           = datasetMeta?.columns ?? [];
  $: numCols        = datasetMeta?.numeric_columns ?? [];
  $: catCols        = datasetMeta?.categorical_columns ?? [];
  $: otherDatasets  = datasets.filter((d: any) => d.id !== datasetId);

  function toggleArr(arr: string[], val: string): string[] {
    return arr.includes(val) ? arr.filter(v => v !== val) : [...arr, val];
  }

  function buildBody(): Record<string, any> {
    const base: Record<string, any> = {
      operation,
      save_as: saveAsName || undefined,
      overwrite,
    };

    switch (operation) {
      case 'scale':
        return { ...base, columns: scaleCols, method: scaleMethod };
      case 'encode':
        return { ...base, column: encodeCol, method: encodeMethod };
      case 'groupby':
        return {
          ...base,
          columns: groupbyCols,
          agg: groupbyAggCol ? { [groupbyAggCol]: groupbyAggFn } : {},
        };
      case 'bin':
        return { ...base, column: binCol, bins: binCount, method: binMethod };
      case 'date_features':
        return { ...base, column: dateFeatCol, features: dateFeats };
      case 'log_transform':
        return { ...base, columns: logCols, base: logBase };
      case 'rolling':
        return { ...base, column: rollingCol, window: rollingWindow, agg: rollingAgg };
      case 'lag':
        return { ...base, column: lagCol, periods: lagPeriods };
      case 'concat':
        return { ...base, dataset_ids: concatIds, axis: concatAxis };
      case 'remove_outliers':
        return { ...base, column: outlierCol, method: outlierMethod, threshold: outlierThreshold };
      case 'pivot':
        return { ...base, index: pivotIndex, columns: pivotColumns, values: pivotValues, aggfunc: pivotAgg };
      default:
        return base;
    }
  }

  async function applyTransform(): Promise<void> {
    if (!datasetId) return;
    loading = true; error = ''; result = null; log = [];
    try {
      const res = await fetch(`${apiBase}/api/v1/transform/${datasetId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildBody()),
      });
      if (!res.ok) { const d = await res.json(); throw new Error(d.detail); }
      const data = await res.json();
      result = data.result;
      log = data.operations_applied;
      dispatch('refresh');
    } catch (e) {
      error = String(e);
    } finally {
      loading = false;
    }
  }

  const OPS: { value: string; label: string }[] = [
    { value: 'scale',           label: 'Escalado'         },
    { value: 'encode',          label: 'Codificacion'     },
    { value: 'groupby',         label: 'Agrupar'          },
    { value: 'bin',             label: 'Binning'          },
    { value: 'date_features',   label: 'Fecha a Features' },
    { value: 'log_transform',   label: 'Log Transform'    },
    { value: 'rolling',         label: 'Rolling Window'   },
    { value: 'lag',             label: 'Lag Feature'      },
    { value: 'concat',          label: 'Concatenar'       },
    { value: 'remove_outliers', label: 'Quitar Outliers'  },
    { value: 'pivot',           label: 'Pivot Table'      },
  ];

  const DATE_FEATS = ['year','month','day','dayofweek','quarter','week','hour','is_weekend'];
</script>

<div class="transform-panel">
  {#if !datasetId}
    <div class="empty-state">
      <p>Selecciona un dataset para transformar.</p>
    </div>
  {:else}
    <h3 class="panel-title">
      Transformar dataset
      <span class="panel-subtitle">{datasetMeta?.name}</span>
    </h3>
    <p class="panel-desc">Aplica una operacion al dataset activo y guarda el resultado como un nuevo dataset.</p>

    <div class="op-grid">
      {#each OPS as op}
        <button
          class="op-btn"
          class:op-btn-active={operation === op.value}
          on:click={() => (operation = op.value)}
        >
          {op.label}
        </button>
      {/each}
    </div>

    <div class="config-card">

      {#if operation === 'scale'}
        <h4 class="section-h4">Escalado numerico</h4>
        <p class="section-desc">Normaliza columnas numericas para que tengan rangos comparables.</p>
        <div class="field">
          <label class="field-label" for="scale-method">Metodo</label>
          <select id="scale-method" class="select" bind:value={scaleMethod}>
            <option value="minmax">Min-Max (0-1)</option>
            <option value="standard">Estandar (media=0, sigma=1)</option>
            <option value="robust">Robusto (usa IQR)</option>
          </select>
        </div>
        <p class="field-label">Columnas a escalar</p>
        <div class="check-grid">
          {#each numCols as col}
            <label class="check-label">
              <input type="checkbox" checked={scaleCols.includes(col)}
                on:change={() => (scaleCols = toggleArr(scaleCols, col))} />
              {col}
            </label>
          {/each}
        </div>

      {:else if operation === 'encode'}
        <h4 class="section-h4">Codificacion categorica</h4>
        <p class="section-desc">Convierte variables categoricas a formato numerico para modelos ML.</p>
        <div class="grid-2">
          <div class="field">
            <label class="field-label" for="encode-col">Columna</label>
            <select id="encode-col" class="select" bind:value={encodeCol}>
              {#each catCols as col}<option value={col}>{col}</option>{/each}
            </select>
          </div>
          <div class="field">
            <label class="field-label" for="encode-method">Metodo</label>
            <select id="encode-method" class="select" bind:value={encodeMethod}>
              <option value="onehot">One-Hot (columnas dummy)</option>
              <option value="label">Label Encoding (enteros)</option>
            </select>
          </div>
        </div>

      {:else if operation === 'groupby'}
        <h4 class="section-h4">Agrupar y agregar</h4>
        <p class="section-desc">Agrupa filas por categorias y calcula estadisticos por grupo.</p>
        <p class="field-label">Columnas de agrupacion</p>
        <div class="check-grid mb-12">
          {#each cols as col}
            <label class="check-label">
              <input type="checkbox" checked={groupbyCols.includes(col)}
                on:change={() => (groupbyCols = toggleArr(groupbyCols, col))} />
              {col}
            </label>
          {/each}
        </div>
        <div class="grid-2">
          <div class="field">
            <label class="field-label" for="groupby-agg-col">Columna a agregar</label>
            <select id="groupby-agg-col" class="select" bind:value={groupbyAggCol}>
              {#each numCols as col}<option value={col}>{col}</option>{/each}
            </select>
          </div>
          <div class="field">
            <label class="field-label" for="groupby-agg-fn">Funcion</label>
            <select id="groupby-agg-fn" class="select" bind:value={groupbyAggFn}>
              {#each ['sum','mean','count','min','max','std'] as fn}
                <option value={fn}>{fn}</option>
              {/each}
            </select>
          </div>
        </div>

      {:else if operation === 'bin'}
        <h4 class="section-h4">Binning (discretizacion)</h4>
        <p class="section-desc">Divide una columna numerica en rangos o cuantiles.</p>
        <div class="grid-3">
          <div class="field">
            <label class="field-label" for="bin-col">Columna</label>
            <select id="bin-col" class="select" bind:value={binCol}>
              {#each numCols as col}<option value={col}>{col}</option>{/each}
            </select>
          </div>
          <div class="field">
            <label class="field-label" for="bin-method">Metodo</label>
            <select id="bin-method" class="select" bind:value={binMethod}>
              <option value="cut">cut (anchos iguales)</option>
              <option value="qcut">qcut (frecuencias iguales)</option>
            </select>
          </div>
          <div class="field">
            <label class="field-label" for="bin-count">Bins</label>
            <input id="bin-count" type="number" class="input" bind:value={binCount} min="2" max="50" />
          </div>
        </div>

      {:else if operation === 'date_features'}
        <h4 class="section-h4">Extraer features de fecha</h4>
        <p class="section-desc">Descompone una columna de fecha en multiples variables numericas.</p>
        <div class="field">
          <label class="field-label" for="date-feat-col">Columna de fecha</label>
          <select id="date-feat-col" class="select" bind:value={dateFeatCol}>
            {#each cols as col}<option value={col}>{col}</option>{/each}
          </select>
        </div>
        <p class="field-label" style="margin-top:12px;">Features a extraer</p>
        <div class="check-grid">
          {#each DATE_FEATS as feat}
            <label class="check-label">
              <input type="checkbox" checked={dateFeats.includes(feat)}
                on:change={() => (dateFeats = toggleArr(dateFeats, feat))} />
              {feat}
            </label>
          {/each}
        </div>

      {:else if operation === 'log_transform'}
        <h4 class="section-h4">Transformacion logaritmica</h4>
        <p class="section-desc">Reduce sesgo en distribuciones asimetricas. Util para variables con cola larga.</p>
        <div class="field">
          <label class="field-label" for="log-base">Base</label>
          <select id="log-base" class="select" bind:value={logBase}>
            <option value="e">Natural (ln)</option>
            <option value="10">Log10</option>
            <option value="2">Log2</option>
          </select>
        </div>
        <p class="field-label">Columnas</p>
        <div class="check-grid">
          {#each numCols as col}
            <label class="check-label">
              <input type="checkbox" checked={logCols.includes(col)}
                on:change={() => (logCols = toggleArr(logCols, col))} />
              {col}
            </label>
          {/each}
        </div>

      {:else if operation === 'rolling'}
        <h4 class="section-h4">Ventana deslizante (Rolling)</h4>
        <p class="section-desc">Calcula estadisticos sobre una ventana temporal. Util para series de tiempo.</p>
        <div class="grid-3">
          <div class="field">
            <label class="field-label" for="rolling-col">Columna</label>
            <select id="rolling-col" class="select" bind:value={rollingCol}>
              {#each numCols as col}<option value={col}>{col}</option>{/each}
            </select>
          </div>
          <div class="field">
            <label class="field-label" for="rolling-agg">Funcion</label>
            <select id="rolling-agg" class="select" bind:value={rollingAgg}>
              {#each ['mean','sum','std','min','max'] as fn}
                <option value={fn}>{fn}</option>
              {/each}
            </select>
          </div>
          <div class="field">
            <label class="field-label" for="rolling-window">Ventana</label>
            <input id="rolling-window" type="number" class="input" bind:value={rollingWindow} min="2" max="365" />
          </div>
        </div>

      {:else if operation === 'lag'}
        <h4 class="section-h4">Feature de lag</h4>
        <p class="section-desc">Crea una copia desplazada de una columna para capturar dependencias temporales.</p>
        <div class="grid-2">
          <div class="field">
            <label class="field-label" for="lag-col">Columna</label>
            <select id="lag-col" class="select" bind:value={lagCol}>
              {#each numCols as col}<option value={col}>{col}</option>{/each}
            </select>
          </div>
          <div class="field">
            <label class="field-label" for="lag-periods">Periodos</label>
            <input id="lag-periods" type="number" class="input" bind:value={lagPeriods} min="1" max="365" />
          </div>
        </div>

      {:else if operation === 'concat'}
        <h4 class="section-h4">Concatenar datasets</h4>
        <p class="section-desc">Une verticalmente (filas) u horizontalmente (columnas) otros datasets cargados.</p>
        <div class="field">
          <label class="field-label" for="concat-axis">Eje</label>
          <select id="concat-axis" class="select" bind:value={concatAxis}>
            <option value={0}>Vertical — apila filas (axis=0)</option>
            <option value={1}>Horizontal — une columnas (axis=1)</option>
          </select>
        </div>
        <p class="field-label">Datasets a concatenar</p>
        {#if otherDatasets.length === 0}
          <p class="hint">No hay otros datasets cargados.</p>
        {:else}
          <div class="check-col">
            {#each otherDatasets as ds}
              <label class="check-label">
                <input type="checkbox" checked={concatIds.includes(ds.id)}
                  on:change={() => (concatIds = toggleArr(concatIds, ds.id))} />
                {ds.name} <span class="muted">({ds.total_rows} filas)</span>
              </label>
            {/each}
          </div>
        {/if}

      {:else if operation === 'remove_outliers'}
        <h4 class="section-h4">Eliminar outliers</h4>
        <p class="section-desc">Filtra filas con valores atipicos usando IQR o Z-Score.</p>
        <div class="grid-3">
          <div class="field">
            <label class="field-label" for="outlier-col">Columna</label>
            <select id="outlier-col" class="select" bind:value={outlierCol}>
              {#each numCols as col}<option value={col}>{col}</option>{/each}
            </select>
          </div>
          <div class="field">
            <label class="field-label" for="outlier-method">Metodo</label>
            <select id="outlier-method" class="select" bind:value={outlierMethod}>
              <option value="iqr">IQR (rango intercuartilico)</option>
              <option value="zscore">Z-Score</option>
            </select>
          </div>
          <div class="field">
            <label class="field-label" for="outlier-threshold">Umbral</label>
            <input id="outlier-threshold" type="number" class="input" bind:value={outlierThreshold} step="0.1" min="0.5" max="10" />
          </div>
        </div>
        <p class="hint">IQR: umbral 1.5 = estandar, 3.0 = conservador. Z-Score: umbral 3 = 3 sigma.</p>

      {:else if operation === 'pivot'}
        <h4 class="section-h4">Tabla pivot</h4>
        <p class="section-desc">Reorganiza el dataset cruzando dos variables, similar a una tabla dinamica de Excel.</p>
        <div class="grid-2">
          <div class="field">
            <label class="field-label" for="pivot-index">Indice (filas)</label>
            <select id="pivot-index" class="select" bind:value={pivotIndex}>
              {#each cols as col}<option value={col}>{col}</option>{/each}
            </select>
          </div>
          <div class="field">
            <label class="field-label" for="pivot-columns">Columnas (cabeceras)</label>
            <select id="pivot-columns" class="select" bind:value={pivotColumns}>
              {#each catCols as col}<option value={col}>{col}</option>{/each}
            </select>
          </div>
          <div class="field">
            <label class="field-label" for="pivot-values">Valores</label>
            <select id="pivot-values" class="select" bind:value={pivotValues}>
              {#each numCols as col}<option value={col}>{col}</option>{/each}
            </select>
          </div>
          <div class="field">
            <label class="field-label" for="pivot-agg">Funcion de agregacion</label>
            <select id="pivot-agg" class="select" bind:value={pivotAgg}>
              {#each ['mean','sum','count','min','max'] as fn}
                <option value={fn}>{fn}</option>
              {/each}
            </select>
          </div>
        </div>
      {/if}
    </div>

    <div class="save-card">
      <p class="field-label">Nombre del resultado (opcional)</p>
      <div class="save-row">
        <input
          class="input flex-1"
          bind:value={saveAsName}
          placeholder="Nombre del nuevo dataset"
        />
        <label class="check-label">
          <input type="checkbox" bind:checked={overwrite} />
          Sobrescribir dataset original
        </label>
      </div>
    </div>

    <button
      class="apply-btn"
      class:apply-btn-loading={loading}
      on:click={applyTransform}
      disabled={loading}
    >
      {loading ? 'Procesando...' : 'Aplicar Transformacion'}
    </button>

    {#if error}
      <div class="alert-error">{error}</div>
    {/if}

    {#if result}
      <div class="result-card">
        <p class="result-title">Transformacion aplicada</p>
        <div class="kpi-grid">
          {#each [
            { l:'Filas',    v: result.total_rows.toLocaleString() },
            { l:'Columnas', v: result.total_features },
          ] as k}
            <div class="kpi-box">
              <div class="kpi-val">{k.v}</div>
              <div class="kpi-label">{k.l}</div>
            </div>
          {/each}
        </div>
        {#if log.length}
          {#each log as l}
            <p class="log-line">- {l}</p>
          {/each}
        {/if}
        <div class="result-actions">
          <button class="btn-primary" on:click={() => dispatch('selectDataset', { id: result!.id })}>
            Ver resultado
          </button>
          <button class="btn-secondary" on:click={() => window.open(`${apiBase}/api/v1/export/${result!.id}`, '_blank')}>
            Descargar CSV
          </button>
        </div>
      </div>
    {/if}
  {/if}
</div>