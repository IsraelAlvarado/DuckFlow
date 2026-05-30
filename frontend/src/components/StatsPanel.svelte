<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import './styles/StatsPanel.css';

  interface DatasetMeta {
    id: string;
    name: string;
    columns: string[];
    numeric_columns: string[];
    categorical_columns: string[];
  }

  export let datasetId: string | null = null;
  export let datasetMeta: DatasetMeta | null = null;
  export let apiBase = 'http://127.0.0.1:8000';

  const dispatch = createEventDispatcher();

  let loading = false;
  let result: any = null;
  let error = '';

  let test = 'outliers';

  let outCol = '';
  let outMethod = 'iqr';
  let outThreshold = 1.5;

  let normCol = '';

  let ttestCol = '';
  let ttestMode = 'group';
  let ttestGroupCol = '';
  let ttestCol2 = '';

  let chi2Col1 = '';
  let chi2Col2 = '';

  let anovaCol = '';
  let anovaGroupCol = '';

  $: cols    = datasetMeta?.columns ?? [];
  $: numCols = datasetMeta?.numeric_columns ?? [];
  $: catCols = datasetMeta?.categorical_columns ?? [];

  function buildBody(): Record<string, any> {
    switch (test) {
      case 'outliers':
        return { test, column: outCol, method: outMethod, threshold: outThreshold };
      case 'normality':
        return { test, column: normCol };
      case 'ttest':
        return ttestMode === 'group'
          ? { test, column: ttestCol, group_column: ttestGroupCol }
          : { test, column: ttestCol, column2: ttestCol2 };
      case 'chi2':
        return { test, column1: chi2Col1, column2: chi2Col2 };
      case 'anova':
        return { test, column: anovaCol, group_column: anovaGroupCol };
      default:
        return { test };
    }
  }

  async function runTest(): Promise<void> {
    if (!datasetId) return;
    loading = true; error = ''; result = null;
    try {
      const res = await fetch(`${apiBase}/api/v1/stats/${datasetId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildBody()),
      });
      if (!res.ok) { const d = await res.json(); throw new Error(d.detail); }
      result = await res.json();
    } catch (e) {
      error = String(e);
    } finally {
      loading = false;
    }
  }

  const TESTS = [
    { value: 'outliers',  label: 'Outliers'      },
    { value: 'normality', label: 'Normalidad'     },
    { value: 'ttest',     label: 'T-Test'         },
    { value: 'chi2',      label: 'Chi-Cuadrado'   },
    { value: 'anova',     label: 'ANOVA'           },
  ];

  function sigColor(sig: boolean): string {
    return sig ? '#166534' : '#92400e';
  }
  function sigBg(sig: boolean): string {
    return sig ? '#f0fdf4' : '#fef9c3';
  }
</script>

<div class="stats-panel">
  {#if !datasetId}
    <div class="empty-state">
      <p>Selecciona un dataset para ejecutar tests estadisticos.</p>
    </div>
  {:else}
    <h3 class="panel-title">
      Analisis estadistico
      <span class="panel-subtitle">{datasetMeta?.name}</span>
    </h3>
    <p class="panel-desc">
      Ejecuta tests estadisticos para validar supuestos y descubrir patrones en tus datos.
    </p>

    <div class="test-selector">
      {#each TESTS as t}
        <button
          class="test-btn"
          class:test-btn-active={test === t.value}
          on:click={() => { test = t.value; result = null; error = ''; }}
        >
          {t.label}
        </button>
      {/each}
    </div>

    <div class="config-card">

      {#if test === 'outliers'}
        <h4 class="section-h4">Deteccion de valores atipicos</h4>
        <p class="section-desc">Identifica valores que se alejan significativamente del resto de la distribucion.</p>
        <div class="grid-3">
          <div class="field">
            <label class="field-label" for="out-col">Columna</label>
            <select id="out-col" class="select" bind:value={outCol}>
              {#each numCols as col}<option value={col}>{col}</option>{/each}
            </select>
          </div>
          <div class="field">
            <label class="field-label" for="out-method">Metodo</label>
            <select id="out-method" class="select" bind:value={outMethod}>
              <option value="iqr">IQR (rango intercuartilico)</option>
              <option value="zscore">Z-Score</option>
            </select>
          </div>
          <div class="field">
            <label class="field-label" for="out-threshold">Umbral</label>
            <input id="out-threshold" type="number" class="input" bind:value={outThreshold} step="0.1" min="0.5" max="10" />
          </div>
        </div>

      {:else if test === 'normality'}
        <h4 class="section-h4">Test de normalidad (Shapiro-Wilk)</h4>
        <p class="section-desc">
          Verifica si una variable sigue una distribucion normal. El test es preciso hasta ~5000 muestras.<br/>
          H0: los datos son normales. Si p &lt; 0.05, se rechaza H0.
        </p>
        <div class="field">
          <label class="field-label" for="norm-col">Columna</label>
          <select id="norm-col" class="select" bind:value={normCol}>
            {#each numCols as col}<option value={col}>{col}</option>{/each}
          </select>
        </div>

      {:else if test === 'ttest'}
        <h4 class="section-h4">T-Test independiente</h4>
        <p class="section-desc">
          Compara las medias de dos grupos o dos columnas para determinar si la diferencia es estadisticamente significativa.
          H0: las medias son iguales.
        </p>
        <div class="field">
          <label class="field-label" for="ttest-col">Columna numerica</label>
          <select id="ttest-col" class="select" bind:value={ttestCol}>
            {#each numCols as col}<option value={col}>{col}</option>{/each}
          </select>
        </div>
        <div class="radio-row">
          <label class="radio-label">
            <input type="radio" name="ttestMode" value="group" bind:group={ttestMode} />
            Comparar por columna de grupo
          </label>
          <label class="radio-label">
            <input type="radio" name="ttestMode" value="col2" bind:group={ttestMode} />
            Comparar dos columnas
          </label>
        </div>
        {#if ttestMode === 'group'}
          <div class="field">
            <label class="field-label" for="ttest-group-col">Columna de grupos</label>
            <select id="ttest-group-col" class="select" bind:value={ttestGroupCol}>
              {#each catCols as col}<option value={col}>{col}</option>{/each}
            </select>
          </div>
          <p class="hint">Se usaran los primeros 2 grupos unicos encontrados.</p>
        {:else}
          <div class="field">
            <label class="field-label" for="ttest-col2">Segunda columna</label>
            <select id="ttest-col2" class="select" bind:value={ttestCol2}>
              {#each numCols.filter(c => c !== ttestCol) as col}<option value={col}>{col}</option>{/each}
            </select>
          </div>
        {/if}

      {:else if test === 'chi2'}
        <h4 class="section-h4">Test Chi-Cuadrado (independencia)</h4>
        <p class="section-desc">
          Evalua si dos variables categoricas son independientes entre si.<br/>
          H0: las variables son independientes. Si p &lt; 0.05 existe asociacion.
        </p>
        <div class="grid-2">
          <div class="field">
            <label class="field-label" for="chi2-col1">Variable 1</label>
            <select id="chi2-col1" class="select" bind:value={chi2Col1}>
              {#each catCols as col}<option value={col}>{col}</option>{/each}
            </select>
          </div>
          <div class="field">
            <label class="field-label" for="chi2-col2">Variable 2</label>
            <select id="chi2-col2" class="select" bind:value={chi2Col2}>
              {#each catCols.filter(c => c !== chi2Col1) as col}<option value={col}>{col}</option>{/each}
            </select>
          </div>
        </div>

      {:else if test === 'anova'}
        <h4 class="section-h4">ANOVA de un factor</h4>
        <p class="section-desc">
          Compara las medias de 3 o mas grupos para detectar diferencias significativas.<br/>
          H0: todas las medias de grupo son iguales. Si p &lt; 0.05, al menos un grupo difiere.
        </p>
        <div class="grid-2">
          <div class="field">
            <label class="field-label" for="anova-col">Variable numerica</label>
            <select id="anova-col" class="select" bind:value={anovaCol}>
              {#each numCols as col}<option value={col}>{col}</option>{/each}
            </select>
          </div>
          <div class="field">
            <label class="field-label" for="anova-group-col">Variable de grupos</label>
            <select id="anova-group-col" class="select" bind:value={anovaGroupCol}>
              {#each catCols as col}<option value={col}>{col}</option>{/each}
            </select>
          </div>
        </div>
      {/if}
    </div>

    <button class="run-btn" class:run-btn-loading={loading} on:click={runTest} disabled={loading}>
      {loading ? 'Ejecutando...' : 'Ejecutar Test'}
    </button>

    {#if error}
      <div class="alert-error">{error}</div>
    {/if}

    {#if result}
      <div class="result-card">
        <div class="result-header">
          <h4 class="result-title">Resultados — {result.test}</h4>
          {#if result.significant !== undefined}
            <span
              class="sig-badge"
              style="background:{sigBg(result.significant)}; color:{sigColor(result.significant)};"
            >
              {result.significant ? 'Significativo (p < 0.05)' : 'No significativo (p >= 0.05)'}
            </span>
          {/if}
        </div>

        {#if result.interpretation}
          <div class="interpretation">{result.interpretation}</div>
        {/if}

        <div class="kpi-grid">
          {#if result.statistic !== undefined}
            <div class="kpi-box">
              <div class="kpi-val">{result.statistic}</div>
              <div class="kpi-label">Estadistico</div>
            </div>
          {/if}
          {#if result.p_value !== undefined}
            <div class="kpi-box">
              <div class="kpi-val" style="color:{result.p_value < 0.05 ? '#059669' : '#d97706'};">{result.p_value}</div>
              <div class="kpi-label">p-valor</div>
            </div>
          {/if}
          {#if result.n !== undefined}
            <div class="kpi-box">
              <div class="kpi-val">{result.n.toLocaleString()}</div>
              <div class="kpi-label">N muestras</div>
            </div>
          {/if}
          {#if result.n_outliers !== undefined}
            <div class="kpi-box">
              <div class="kpi-val" style="color:{result.n_outliers > 0 ? '#d97706' : '#059669'};">{result.n_outliers}</div>
              <div class="kpi-label">Outliers</div>
            </div>
          {/if}
          {#if result.pct_outliers !== undefined}
            <div class="kpi-box">
              <div class="kpi-val">{result.pct_outliers}%</div>
              <div class="kpi-label">% Outliers</div>
            </div>
          {/if}
          {#if result.normal !== undefined}
            <div class="kpi-box">
              <div class="kpi-val" style="color:{result.normal ? '#059669' : '#ef4444'};">{result.normal ? 'Si' : 'No'}</div>
              <div class="kpi-label">Normal?</div>
            </div>
          {/if}
          {#if result.skewness !== undefined}
            <div class="kpi-box">
              <div class="kpi-val">{result.skewness}</div>
              <div class="kpi-label">Asimetria</div>
            </div>
          {/if}
          {#if result.kurtosis !== undefined}
            <div class="kpi-box">
              <div class="kpi-val">{result.kurtosis}</div>
              <div class="kpi-label">Curtosis</div>
            </div>
          {/if}
          {#if result.degrees_of_freedom !== undefined}
            <div class="kpi-box">
              <div class="kpi-val">{result.degrees_of_freedom}</div>
              <div class="kpi-label">Grados libertad</div>
            </div>
          {/if}
        </div>

        {#if result.lower_bound !== undefined}
          <div class="five-grid">
            {#each [
              { l:'Min',     v: result.stats?.min    },
              { l:'Q1',      v: result.stats?.q1     },
              { l:'Mediana', v: result.stats?.median  },
              { l:'Q3',      v: result.stats?.q3     },
              { l:'Max',     v: result.stats?.max    },
            ] as s}
              <div class="mini-kpi">
                <div class="mini-val">{s.v}</div>
                <div class="mini-label">{s.l}</div>
              </div>
            {/each}
          </div>
          <p class="hint">Limites de deteccion: [{result.lower_bound}, {result.upper_bound}]</p>
          {#if result.sample_outliers?.length}
            <p class="subsection-title">Muestra de outliers:</p>
            <div class="outlier-chips">
              {#each result.sample_outliers.slice(0, 20) as v}
                <span class="chip">{v}</span>
              {/each}
            </div>
          {/if}
        {/if}

        {#if result.group_1}
          <div class="grid-2" style="margin-top:8px;">
            {#each [result.group_1, result.group_2] as g}
              <div class="group-box">
                <p class="group-title">Grupo: {g.label}</p>
                <div class="grid-3">
                  {#each [{ l:'N', v: g.n }, { l:'Media', v: g.mean }, { l:'Std', v: g.std }] as s}
                    <div class="text-center">
                      <div class="mini-val">{s.v}</div>
                      <div class="mini-label">{s.l}</div>
                    </div>
                  {/each}
                </div>
              </div>
            {/each}
          </div>
        {/if}

        {#if result.group_stats?.length}
          <div class="table-wrap" style="margin-top:12px;">
            <p class="subsection-title">Estadisticos por grupo:</p>
            <table class="data-table">
              <thead>
                <tr>
                  {#each ['Grupo','N','Media','Std'] as h}
                    <th>{h}</th>
                  {/each}
                </tr>
              </thead>
              <tbody>
                {#each result.group_stats as g}
                  <tr>
                    <td class="td-strong">{g.group}</td>
                    <td>{g.n}</td>
                    <td>{g.mean}</td>
                    <td>{g.std}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {/if}
      </div>
    {/if}
  {/if}
</div>