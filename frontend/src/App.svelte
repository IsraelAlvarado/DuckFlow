<script lang="ts">
  import { onMount } from 'svelte';
  import DatasetManager from './components/DatasetManager.svelte';
  import EdaPanel from './components/EdaPanel.svelte';
  import CleaningPanel from './components/CleaningPanel.svelte';
  import MergePanel from './components/MergePanel.svelte';
  import KagglePanel from './components/KagglePanel.svelte';
  import TransformPanel from './components/TransformPanel.svelte';
  import StoragePanel from './components/Storagepanel.svelte';
  import TrainPanel from './components/TrainPanel.svelte';
  import Chart from './components/Chart.svelte';
  import type { EChartsOption } from 'echarts';

  const API = 'http://127.0.0.1:8000';

  interface Dataset {
    id: string;
    name: string;
    total_rows: number;
    total_features: number;
    columns: string[];
    numeric_columns: string[];
    categorical_columns: string[];
    missing_total: number;
    duplicates: number;
    memory_kb: number;
  }

  let datasets: Dataset[] = [];
  let selectedDatasetId: string | null = null;
  let activeTab = 'eda';
  let sidebarOpen = false;

  // ── Chart state ──────────────────────────────────────────────────────
  let chartLoading = false;
  let chartError   = '';
  let chartOptions: EChartsOption = {};
  let chartCatCol  = '';
  let chartNumCol  = '';
  let chartNumCol2 = '';
  let chartType    = 'bar';

  const CHART_TYPES = [
    { value: 'bar',       label: 'Barras'        },
    { value: 'pie',       label: 'Dona / Pie'    },
    { value: 'line',      label: 'Distribución'  },
    { value: 'scatter',   label: 'Dispersión'    },
    { value: 'box',       label: 'Cajas (Box)'   },
    { value: 'heatmap',   label: 'Heatmap Corr.' },
    { value: 'treemap',   label: 'Treemap'       },
    { value: 'histogram', label: 'Histograma'    },
    { value: 'funnel',    label: 'Embudo'        },
    { value: 'radar',     label: 'Radar'         },
  ];

  // ── Export analysis ───────────────────────────────────────────────────
  let showExportPanel   = false;
  let exportFormat: 'py' | 'ipynb' = 'ipynb';
  let exportLoading     = false;
  let exportError       = '';
  const ALL_SECTIONS = [
    { id: 'overview',      label: 'Resumen general'          },
    { id: 'missing',       label: 'Valores faltantes'        },
    { id: 'numeric',       label: 'Estadísticas numéricas'   },
    { id: 'categorical',   label: 'Estadísticas categóricas' },
    { id: 'correlation',   label: 'Correlación'              },
    { id: 'distributions', label: 'Distribuciones'           },
    { id: 'outliers',      label: 'Outliers (IQR)'           },
    { id: 'normality',     label: 'Test de normalidad'       },
  ];
  let selectedSections: string[] = ALL_SECTIONS.map(s => s.id);

  function toggleSection(id: string): void {
    selectedSections = selectedSections.includes(id)
      ? selectedSections.filter(s => s !== id)
      : [...selectedSections, id];
  }
  function toggleAllSections(): void {
    selectedSections = selectedSections.length === ALL_SECTIONS.length
      ? [] : ALL_SECTIONS.map(s => s.id);
  }

  async function downloadAnalysis(): Promise<void> {
    if (!selectedDatasetId || selectedSections.length === 0) return;
    exportLoading = true; exportError = '';
    try {
      const res = await fetch(`${API}/api/v1/export-analysis/${selectedDatasetId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ format: exportFormat, sections: selectedSections }),
      });
      if (!res.ok) { const d = await res.json(); throw new Error(d.detail ?? 'Error al exportar'); }
      const blob = await res.blob();
      const cd   = res.headers.get('Content-Disposition') ?? '';
      const m    = cd.match(/filename="(.+?)"/);
      const fn   = m ? m[1] : `analisis.${exportFormat}`;
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement('a');
      a.href = url; a.download = fn; a.click();
      URL.revokeObjectURL(url);
      showExportPanel = false;
    } catch (e) { exportError = String(e); }
    finally { exportLoading = false; }
  }

  $: selectedMeta = datasets.find((d: Dataset) => d.id === selectedDatasetId) ?? null;
  $: if (selectedMeta && activeTab === 'chart') refreshChartCols(selectedMeta);

  async function refreshDatasets(): Promise<void> {
    try {
      const res  = await fetch(`${API}/api/v1/datasets`);
      const data = await res.json();
      datasets = data.datasets;
    } catch (e) { console.error(e); }
  }

  function selectDataset(id: string | null): void {
    selectedDatasetId = id;
    sidebarOpen       = false;
    showExportPanel   = false;
  }

  function refreshChartCols(meta: Dataset): void {
    if (!meta) return;
    if (!chartCatCol || !meta.categorical_columns.includes(chartCatCol))
      chartCatCol = meta.categorical_columns[0] ?? '';
    if (!chartNumCol || !meta.numeric_columns.includes(chartNumCol))
      chartNumCol = meta.numeric_columns[0] ?? '';
    if (!chartNumCol2 || !meta.numeric_columns.includes(chartNumCol2))
      chartNumCol2 = meta.numeric_columns[1] ?? meta.numeric_columns[0] ?? '';
  }

  const needsCat  = ['bar', 'pie', 'treemap', 'funnel', 'radar'];
  const needsNum2 = ['scatter'];
  const numOnly   = ['line', 'box', 'histogram'];

  async function buildChart(): Promise<void> {
    if (!selectedDatasetId) return;
    chartLoading = true; chartError = '';
    try {
      const res = await fetch(`${API}/api/v1/eda/${selectedDatasetId}`);
      if (!res.ok) throw new Error('Error cargando EDA');
      const eda = await res.json();

      const catStat  = eda.categorical_stats?.find((s: any) => s.column === chartCatCol);
      const catData: { name: string; value: number }[] = catStat?.top_10 ?? [];
      const dist     = eda.distributions?.[chartNumCol];
      const numStats = eda.numeric_stats ?? [];

      switch (chartType) {
        case 'bar':
          chartOptions = {
            title: { text: `${chartCatCol} — Top valores`, left: 'center', textStyle: { fontSize: 13 } },
            tooltip: { trigger: 'axis' },
            grid: { top: 48, bottom: 70, left: 60, right: 20 },
            xAxis: { type: 'category', data: catData.map(d => d.name), axisLabel: { rotate: 30, fontSize: 11 } },
            yAxis: { type: 'value' },
            series: [{ type: 'bar', data: catData.map(d => d.value), itemStyle: { color: '#3b82f6', borderRadius: [4,4,0,0] } }],
          }; break;

        case 'pie':
          chartOptions = {
            title: { text: `${chartCatCol}`, left: 'center', textStyle: { fontSize: 13 } },
            tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
            legend: { bottom: 0, type: 'scroll' },
            series: [{ name: chartCatCol, type: 'pie', radius: ['35%','65%'],
                       avoidLabelOverlap: false,
                       itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 2 },
                       data: catData.map(d => ({ name: d.name, value: d.value })) }],
          }; break;

        case 'line':
          if (!dist) throw new Error('Sin distribución para esta columna');
          chartOptions = {
            title: { text: `Distribución de ${chartNumCol}`, left: 'center', textStyle: { fontSize: 13 } },
            tooltip: { trigger: 'axis' },
            grid: { top: 48, bottom: 70, left: 60, right: 20 },
            xAxis: { type: 'category',
                     data: dist.bins.slice(0,-1).map((b: number, i: number) => `${b.toFixed(1)}-${dist.bins[i+1].toFixed(1)}`),
                     axisLabel: { rotate: 30, fontSize: 10, interval: 2 } },
            yAxis: { type: 'value' },
            series: [{ type: 'line', data: dist.counts, smooth: true,
                       areaStyle: { opacity: 0.2 },
                       itemStyle: { color: '#8b5cf6' }, lineStyle: { width: 2 } }],
          }; break;

        case 'scatter': {
          const raw = await fetch(`${API}/api/v1/export/${selectedDatasetId}`);
          const text = await raw.text();
          const rows = text.trim().split('\n');
          const header = rows[0].split(',');
          const xi = header.indexOf(chartNumCol);
          const yi = header.indexOf(chartNumCol2);
          if (xi < 0 || yi < 0) throw new Error('Columnas no encontradas en CSV');
          const scatterData = rows.slice(1).map(r => {
            const cols = r.split(',');
            return [parseFloat(cols[xi]), parseFloat(cols[yi])];
          }).filter(([x,y]) => !isNaN(x) && !isNaN(y));
          chartOptions = {
            title: { text: `${chartNumCol} vs ${chartNumCol2}`, left: 'center', textStyle: { fontSize: 13 } },
            tooltip: { trigger: 'item', formatter: (p: any) => `${chartNumCol}: ${p.value[0]}<br/>${chartNumCol2}: ${p.value[1]}` },
            grid: { top: 48, bottom: 50, left: 70, right: 20 },
            xAxis: { type: 'value', name: chartNumCol, nameLocation: 'middle', nameGap: 30 },
            yAxis: { type: 'value', name: chartNumCol2, nameLocation: 'middle', nameGap: 50 },
            series: [{ type: 'scatter', data: scatterData, symbolSize: 5, itemStyle: { color: '#f59e0b', opacity: 0.6 } }],
          }; break;
        }

        case 'box': {
          const boxCols = selectedMeta?.numeric_columns.slice(0, 8) ?? [];
          const boxData: [number, number, number, number, number][] = boxCols
            .map(col => {
              const s = numStats.find((n: any) => n.column === col);
              if (!s) return null;
              return [s.min, s.q25, s.median, s.q75, s.max] as [number, number, number, number, number];
            })
            .filter((v): v is [number, number, number, number, number] => v !== null);
          chartOptions = {
            title: { text: 'Box plots — variables numéricas', left: 'center', textStyle: { fontSize: 13 } },
            tooltip: { trigger: 'item' },
            grid: { top: 48, bottom: 70, left: 60, right: 20 },
            xAxis: { type: 'category', data: boxCols, axisLabel: { rotate: 30, fontSize: 10 } },
            yAxis: { type: 'value' },
            series: [{ name: 'boxplot', type: 'boxplot', data: boxData,
                       itemStyle: { color: '#eff6ff', borderColor: '#3b82f6', borderWidth: 2 },
                       boxWidth: ['20%', '50%'] }],
          }; break;
        }

        case 'heatmap': {
          const corr = eda.correlation;
          if (!corr?.columns?.length) throw new Error('Se necesitan columnas numéricas para correlación');
          const cols = corr.columns;
          const heatData: [number,number,number][] = [];
          for (let i = 0; i < cols.length; i++)
            for (let j = 0; j < cols.length; j++)
              heatData.push([i, j, corr.matrix[i][j] ?? 0]);
          chartOptions = {
            title: { text: 'Matriz de correlación', left: 'center', textStyle: { fontSize: 13 } },
            tooltip: { formatter: (p: any) => `${cols[p.value[1]]} / ${cols[p.value[0]]}<br/>r = ${p.value[2]}` },
            grid: { top: 48, bottom: 80, left: 120, right: 20 },
            xAxis: { type: 'category', data: cols, axisLabel: { rotate: 45, fontSize: 10 } },
            yAxis: { type: 'category', data: cols, axisLabel: { fontSize: 10 } },
            visualMap: { min: -1, max: 1, calculable: true, orient: 'horizontal',
                         left: 'center', bottom: 0,
                         inRange: { color: ['#3b82f6','#f8fafc','#ef4444'] } },
            series: [{ type: 'heatmap', data: heatData, label: { show: cols.length <= 8, fontSize: 9 } }],
          }; break;
        }

        case 'treemap':
          if (!catData.length) throw new Error('Sin datos categóricos');
          chartOptions = {
            title: { text: `Treemap — ${chartCatCol}`, left: 'center', textStyle: { fontSize: 13 } },
            tooltip: { formatter: (p: any) => `${p.name}: ${p.value}` },
            series: [{
              type: 'treemap',
              data: catData.map(d => ({ name: d.name, value: d.value })),
              roam: false, breadcrumb: { show: false },
              label: { show: true, fontSize: 11 },
              itemStyle: { borderWidth: 2, borderColor: '#fff' },
              levels: [{ itemStyle: { borderWidth: 3, borderColor: '#fff', gapWidth: 3 } }],
            }],
          }; break;

        case 'histogram':
          if (!dist) throw new Error('Sin datos de distribución');
          chartOptions = {
            title: { text: `Histograma — ${chartNumCol}`, left: 'center', textStyle: { fontSize: 13 } },
            tooltip: { trigger: 'axis' },
            grid: { top: 48, bottom: 70, left: 60, right: 20 },
            xAxis: { type: 'category',
                     data: dist.bins.slice(0,-1).map((b: number) => `${b.toFixed(1)}`),
                     axisLabel: { rotate: 30, fontSize: 10, interval: 2 } },
            yAxis: { type: 'value', name: 'Frecuencia' },
            series: [{ type: 'bar', data: dist.counts, barCategoryGap: '2%',
                       itemStyle: { color: '#10b981', borderRadius: [2,2,0,0] } }],
          }; break;

        case 'funnel':
          if (!catData.length) throw new Error('Sin datos categóricos');
          chartOptions = {
            title: { text: `Embudo — ${chartCatCol}`, left: 'center', textStyle: { fontSize: 13 } },
            tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
            series: [{
              type: 'funnel', left: '10%', width: '80%', top: 48,
              data: [...catData].sort((a,b) => b.value - a.value).slice(0,8).map(d => ({ name: d.name, value: d.value })),
              label: { position: 'inside', formatter: '{b}\n{d}%', fontSize: 11 },
              itemStyle: { borderWidth: 1, borderColor: '#fff' },
            }],
          }; break;

        case 'radar': {
          const radarCols = selectedMeta?.numeric_columns.slice(0, 7) ?? [];
          if (radarCols.length < 3) throw new Error('Se necesitan al menos 3 columnas numéricas');
          const indicators = radarCols.map(col => {
            const s = numStats.find((n: any) => n.column === col);
            return { name: col, max: s ? s.max : 1 };
          });
          const values = radarCols.map(col => {
            const s = numStats.find((n: any) => n.column === col);
            return s ? s.mean ?? 0 : 0;
          });
          chartOptions = {
            title: { text: 'Radar — medias de variables numéricas', left: 'center', textStyle: { fontSize: 13 } },
            tooltip: {},
            radar: { indicator: indicators, center: ['50%','55%'], radius: '65%' },
            series: [{ type: 'radar',
                       data: [{ value: values, name: 'Media',
                                areaStyle: { opacity: 0.25 },
                                lineStyle: { color: '#6366f1', width: 2 },
                                itemStyle: { color: '#6366f1' } }] }],
          }; break;
        }
      }
    } catch (e) {
      chartError = String(e);
    } finally {
      chartLoading = false;
    }
  }

  onMount(refreshDatasets);

  const tabs = [
    { id: 'eda',       label: 'Análisis'   },
    { id: 'clean',     label: 'Limpiar'    },
    { id: 'transform', label: 'Transformar'},
    { id: 'merge',     label: 'Combinar'   },
    { id: 'train',     label: 'Entrenar'   },
    { id: 'chart',     label: 'Gráficas'   },
    { id: 'kaggle',    label: 'Kaggle'     },
    { id: 'storage',   label: 'Almacén'    },
  ];
</script>

<!-- Sidebar overlay (mobile) -->
{#if sidebarOpen}
  <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
  <div class="sidebar-overlay" on:click={() => (sidebarOpen = false)}></div>
{/if}

<!-- Export panel overlay -->
{#if showExportPanel}
  <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
  <div class="export-overlay" on:click={() => (showExportPanel = false)}></div>
  <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
  <div class="export-panel" on:click|stopPropagation>
    <div class="export-panel-header">
      <h3 class="export-panel-title">Exportar análisis</h3>
      <button class="export-close" on:click={() => (showExportPanel = false)}>×</button>
    </div>
    <p class="export-desc">Genera un archivo con el análisis completo, incluyendo resultados reales calculados y código reproducible.</p>
    <p class="export-label">Formato</p>
    <div class="format-row">
      {#each [['ipynb','nb','Jupyter Notebook','.ipynb — celdas ejecutables'],['py','py','Script Python','.py — archivo plano']] as [val,icon,title,sub]}
        <button class="format-btn" class:format-active={exportFormat === val}
          on:click={() => (exportFormat = val as 'py'|'ipynb')}>
          <span class="format-icon">{icon}</span>
          <span><strong>{title}</strong><small>{sub}</small></span>
        </button>
      {/each}
    </div>
    <div class="sections-header">
      <p class="export-label">Secciones</p>
      <button class="toggle-all-btn" on:click={toggleAllSections}>
        {selectedSections.length === ALL_SECTIONS.length ? 'Ninguna' : 'Todas'}
      </button>
    </div>
    <div class="sections-grid">
      {#each ALL_SECTIONS as sec, i}
        <label class="section-check" class:section-selected={selectedSections.includes(sec.id)}>
          <input type="checkbox" checked={selectedSections.includes(sec.id)}
            on:change={() => toggleSection(sec.id)} />
          <span class="section-num">{String(i+1).padStart(2,'0')}</span>
          {sec.label}
        </label>
      {/each}
    </div>
    {#if exportError}<div class="export-error">{exportError}</div>{/if}
    <button class="download-btn"
      disabled={exportLoading || selectedSections.length === 0 || !selectedDatasetId}
      on:click={downloadAnalysis}>
      {exportLoading ? 'Generando...' : `Descargar .${exportFormat}`}
    </button>
    {#if selectedSections.length === 0}<p class="export-warn">Selecciona al menos una sección.</p>{/if}
  </div>
{/if}

<!-- ── Main layout ── -->
<div class="app-layout">

  <!-- Sidebar -->
  <div class="sidebar-wrapper" class:sidebar-open={sidebarOpen}>
    <DatasetManager
      {datasets}
      selectedId={selectedDatasetId}
      apiBase={API}
      on:refresh={refreshDatasets}
      on:select={(e) => selectDataset(e.detail.id)}
    />
  </div>

  <!-- Content -->
  <div class="main-content">

    <!-- Topbar -->
    <div class="topbar">
      <button class="menu-btn" on:click={() => (sidebarOpen = !sidebarOpen)} aria-label="Menu">
        <span></span><span></span><span></span>
      </button>
      <div class="tab-list">
        {#each tabs as tab}
          <button class="tab-btn" class:tab-active={activeTab === tab.id}
            on:click={() => (activeTab = tab.id)}>{tab.label}</button>
        {/each}
      </div>
      {#if selectedMeta}
        <div class="topbar-meta">
          <span class="meta-name">{selectedMeta.name}</span>
          <span class="meta-dim">{selectedMeta.total_rows.toLocaleString()} × {selectedMeta.total_features}</span>
          <button class="analysis-btn" on:click={() => (showExportPanel = !showExportPanel)}>
            Exportar análisis
          </button>
          <button class="export-btn"
            on:click={() => window.open(`${API}/api/v1/export/${selectedDatasetId}`, '_blank')}>
            Exportar CSV
          </button>
        </div>
      {/if}
    </div>

    <!-- Panel area -->
    <div class="panel-area">

      {#if activeTab === 'eda'}
        <EdaPanel datasetId={selectedDatasetId} apiBase={API} />

      {:else if activeTab === 'clean'}
        <CleaningPanel
          datasetId={selectedDatasetId}
          datasetMeta={selectedMeta}
          apiBase={API}
          on:refresh={refreshDatasets}
          on:selectDataset={(e) => { selectDataset(e.detail.id); activeTab = 'eda'; }}
        />

      {:else if activeTab === 'transform'}
        <TransformPanel
          datasetId={selectedDatasetId}
          datasetMeta={selectedMeta}
          {datasets}
          apiBase={API}
          on:refresh={refreshDatasets}
          on:selectDataset={(e) => { selectDataset(e.detail.id); activeTab = 'eda'; }}
        />

      {:else if activeTab === 'merge'}
        <MergePanel
          {datasets}
          apiBase={API}
          on:refresh={refreshDatasets}
          on:selectDataset={(e) => { selectDataset(e.detail.id); activeTab = 'eda'; }}
        />

      {:else if activeTab === 'train'}
        <TrainPanel
          datasetId={selectedDatasetId}
          datasetMeta={selectedMeta}
          apiBase={API}
          on:refresh={refreshDatasets}
          on:selectDataset={(e) => { selectDataset(e.detail.id); activeTab = 'eda'; }}
        />

      {:else if activeTab === 'chart'}
        <div class="scroll-panel">
          {#if !selectedDatasetId}
            <div class="empty-panel">
              <p>Selecciona un dataset para visualizar gráficas.</p>
            </div>
          {:else}
            <div class="chart-config">
              <div class="chart-type-row">
                {#each CHART_TYPES as ct}
                  <button
                    class="ct-btn"
                    class:ct-active={chartType === ct.value}
                    on:click={() => { chartType = ct.value; chartOptions = {}; chartError = ''; }}
                  >{ct.label}</button>
                {/each}
              </div>

              <div class="col-selectors">
                {#if needsCat.includes(chartType) && selectedMeta?.categorical_columns?.length}
                  <div class="field-group">
                    <label class="field-label" for="chart-cat">Categoría</label>
                    <select id="chart-cat" class="select" bind:value={chartCatCol}>
                      {#each selectedMeta.categorical_columns as col}
                        <option value={col}>{col}</option>
                      {/each}
                    </select>
                  </div>
                {/if}

                {#if !needsCat.includes(chartType) || needsNum2.includes(chartType) || numOnly.includes(chartType)}
                  {#if selectedMeta?.numeric_columns?.length}
                    <div class="field-group">
                      <label class="field-label" for="chart-num">
                        {needsNum2.includes(chartType) ? 'Eje X' : 'Métrica'}
                      </label>
                      <select id="chart-num" class="select" bind:value={chartNumCol}>
                        {#each selectedMeta.numeric_columns as col}
                          <option value={col}>{col}</option>
                        {/each}
                      </select>
                    </div>
                  {/if}
                {/if}

                {#if needsNum2.includes(chartType) && selectedMeta?.numeric_columns?.length}
                  <div class="field-group">
                    <label class="field-label" for="chart-num2">Eje Y</label>
                    <select id="chart-num2" class="select" bind:value={chartNumCol2}>
                      {#each selectedMeta.numeric_columns as col}
                        <option value={col}>{col}</option>
                      {/each}
                    </select>
                  </div>
                {/if}

                {#if chartType === 'heatmap' || chartType === 'box' || chartType === 'radar'}
                  <div class="field-group" style="align-self:flex-end;">
                    <p class="field-label" style="margin-bottom:4px;">Auto-selección</p>
                    <span style="font-size:11px;color:#64748b;line-height:1.4;">
                      Usa todas las columnas numéricas disponibles.
                    </span>
                  </div>
                {/if}

                <button class="btn-generate" on:click={buildChart} disabled={chartLoading}>
                  {chartLoading ? '...' : 'Generar'}
                </button>
              </div>
            </div>

            {#if chartError}
              <div class="alert-error">{chartError}</div>
            {/if}

            {#if chartOptions && Object.keys(chartOptions).length > 0}
              <div class="chart-container">
                <Chart options={chartOptions} />
              </div>
            {:else if !chartLoading}
              <div class="chart-placeholder">
                Elige un tipo de gráfica y pulsa "Generar".
              </div>
            {/if}
          {/if}
        </div>

      {:else if activeTab === 'kaggle'}
        <KagglePanel
          {datasets}
          apiBase={API}
          selectedDatasetId={selectedDatasetId}
          on:refresh={refreshDatasets}
        />

      {:else if activeTab === 'storage'}
        <StoragePanel
          apiBase={API}
          {datasets}
          on:refresh={refreshDatasets}
        />
      {/if}

    </div>
  </div>
</div>

<style>
  :global(html, body) {
    margin: 0; padding: 0;
    width: 100%; height: 100%;
    overflow: hidden;
    box-sizing: border-box;
  }
  :global(*, *::before, *::after) { box-sizing: border-box; }
  :global(#app) {
    width: 100%; height: 100vh;
    margin: 0; padding: 0;
    max-width: none;
    border: none;
    display: block;
  }

  .app-layout {
    display: flex;
    width: 100vw;
    height: 100vh;
    overflow: hidden;
    font-family: system-ui, -apple-system, sans-serif;
    background: #f8fafc;
    color: #334155;
  }

  .sidebar-wrapper {
    width: 272px;
    min-width: 240px;
    flex-shrink: 0;
    height: 100vh;
    z-index: 200;
    overflow: hidden;
  }

  .sidebar-overlay { display: none; }

  .main-content {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    height: 100vh;
    overflow: hidden;
  }

  .topbar {
    display: flex;
    align-items: center;
    gap: 4px;
    background: white;
    border-bottom: 1px solid #e2e8f0;
    padding: 0 12px;
    height: 48px;
    flex-shrink: 0;
    overflow-x: auto;
    scrollbar-width: none;
  }
  .topbar::-webkit-scrollbar { display: none; }

  .menu-btn {
    display: none;
    flex-direction: column;
    gap: 4px;
    background: none;
    border: none;
    cursor: pointer;
    padding: 6px;
    flex-shrink: 0;
  }
  .menu-btn span { display: block; width: 20px; height: 2px; background: #334155; border-radius: 2px; }

  .tab-list { display: flex; gap: 2px; flex-shrink: 0; }
  .tab-btn {
    padding: 5px 10px;
    border: none; border-radius: 6px;
    font-size: 12.5px; font-weight: 600;
    cursor: pointer;
    transition: all 0.15s;
    background: transparent; color: #64748b;
    white-space: nowrap;
  }
  .tab-btn:hover { background: #f1f5f9; color: #0f172a; }
  .tab-active { background: #0f172a !important; color: white !important; }

  .topbar-meta {
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 6px;
    flex-shrink: 0;
  }
  .meta-name {
    font-size: 12px; font-weight: 600; color: #0f172a;
    white-space: nowrap; max-width: 140px;
    overflow: hidden; text-overflow: ellipsis;
  }
  .meta-dim { font-size: 11px; color: #64748b; white-space: nowrap; }

  .export-btn {
    padding: 4px 9px;
    background: #f1f5f9; border: 1px solid #e2e8f0; border-radius: 5px;
    font-size: 11px; font-weight: 600; cursor: pointer; color: #334155;
    white-space: nowrap; transition: background 0.15s;
  }
  .export-btn:hover { background: #e2e8f0; }

  .analysis-btn {
    padding: 4px 9px;
    background: #0f172a; border: none; border-radius: 5px;
    font-size: 11px; font-weight: 600; cursor: pointer; color: white;
    white-space: nowrap; transition: opacity 0.15s;
  }
  .analysis-btn:hover { opacity: 0.85; }

  .panel-area {
    flex: 1;
    min-height: 0;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }

  .scroll-panel {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
    min-height: 0;
  }

  .chart-config {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 12px 14px;
    margin-bottom: 14px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .chart-type-row { display: flex; gap: 6px; flex-wrap: wrap; }

  .ct-btn {
    padding: 5px 11px;
    border: 1.5px solid #e2e8f0;
    border-radius: 6px;
    font-size: 11.5px; font-weight: 500;
    cursor: pointer; background: white; color: #64748b;
    transition: all 0.13s; white-space: nowrap;
  }
  .ct-btn:hover { border-color: #94a3b8; color: #0f172a; }
  .ct-active { border-color: #0f172a; background: #0f172a; color: white; font-weight: 700; }

  .col-selectors { display: flex; gap: 10px; flex-wrap: wrap; align-items: flex-end; }

  .field-group { display: flex; flex-direction: column; gap: 3px; }
  .field-label { font-size: 10px; font-weight: 700; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; }
  .select { padding: 6px 9px; border: 1px solid #e2e8f0; border-radius: 5px; font-size: 12px; color: #334155; background: white; }

  .btn-generate {
    padding: 7px 18px;
    background: #0f172a; color: white;
    border: none; border-radius: 6px;
    font-size: 12px; font-weight: 700;
    cursor: pointer; transition: opacity 0.15s;
    align-self: flex-end;
  }
  .btn-generate:disabled { opacity: 0.5; cursor: not-allowed; }

  .chart-container {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 16px;
    height: calc(100vh - 340px);
    min-height: 300px;
  }

  .chart-placeholder {
    display: flex; align-items: center; justify-content: center;
    height: 200px;
    background: white; border: 1px dashed #cbd5e1; border-radius: 8px;
    color: #94a3b8; font-size: 13px;
  }

  .alert-error {
    padding: 10px 14px; background: #fee2e2; color: #991b1b;
    border-radius: 7px; margin-bottom: 14px; font-size: 13px;
  }

  .empty-panel {
    display: flex; align-items: center; justify-content: center;
    height: 300px; color: #94a3b8; font-size: 14px;
  }

  .export-overlay {
    position: fixed; inset: 0;
    background: rgba(0,0,0,0.35); z-index: 500;
  }
  .export-panel {
    position: fixed; top: 50%; left: 50%;
    transform: translate(-50%, -50%);
    z-index: 501;
    background: white; border-radius: 12px;
    padding: 22px;
    width: 480px; max-width: calc(100vw - 32px);
    max-height: 85vh; overflow-y: auto;
    box-shadow: 0 20px 60px rgba(0,0,0,0.25);
  }
  .export-panel-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
  .export-panel-title  { margin: 0; font-size: 15px; font-weight: 700; color: #0f172a; }
  .export-close        { background: none; border: none; font-size: 22px; cursor: pointer; color: #94a3b8; line-height: 1; padding: 0 4px; }
  .export-close:hover  { color: #0f172a; }
  .export-desc         { margin: 0 0 16px; font-size: 12px; color: #64748b; line-height: 1.5; }
  .export-label        { margin: 0 0 7px; font-size: 10px; font-weight: 700; color: #64748b; text-transform: uppercase; letter-spacing: 0.6px; }
  .format-row          { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 18px; }
  .format-btn {
    display: flex; align-items: center; gap: 8px;
    padding: 10px; border: 2px solid #e2e8f0; border-radius: 7px;
    background: white; cursor: pointer; text-align: left; transition: all 0.15s;
  }
  .format-btn:hover  { border-color: #94a3b8; }
  .format-active     { border-color: #0f172a; background: #f8fafc; }
  .format-icon {
    width: 30px; height: 30px; border-radius: 5px;
    background: #0f172a; color: white;
    font-size: 9px; font-weight: 700; font-family: monospace;
    display: flex; align-items: center; justify-content: center; flex-shrink: 0;
  }
  .format-btn span:last-child { display: flex; flex-direction: column; gap: 2px; }
  .format-btn strong { font-size: 12px; color: #0f172a; }
  .format-btn small  { font-size: 10px; color: #94a3b8; }
  .sections-header   { display: flex; justify-content: space-between; align-items: center; margin-bottom: 7px; }
  .toggle-all-btn    { background: none; border: 1px solid #e2e8f0; border-radius: 4px; padding: 2px 7px; font-size: 11px; color: #64748b; cursor: pointer; }
  .toggle-all-btn:hover { background: #f1f5f9; }
  .sections-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 5px; margin-bottom: 16px; }
  .section-check {
    display: flex; align-items: center; gap: 6px;
    padding: 7px 9px; border: 1px solid #e2e8f0; border-radius: 5px;
    cursor: pointer; font-size: 11px; color: #475569;
    transition: all 0.12s; user-select: none;
  }
  .section-check:hover   { border-color: #94a3b8; }
  .section-selected      { border-color: #0f172a; background: #f8fafc; color: #0f172a; font-weight: 600; }
  .section-check input   { display: none; }
  .section-num           { font-size: 9px; font-weight: 700; font-family: monospace; color: #94a3b8; flex-shrink: 0; }
  .section-selected .section-num { color: #0f172a; }
  .download-btn {
    width: 100%; padding: 10px;
    background: #0f172a; color: white; border: none; border-radius: 6px;
    font-size: 13px; font-weight: 700; cursor: pointer; transition: opacity 0.15s;
  }
  .download-btn:disabled     { opacity: 0.4; cursor: not-allowed; }
  .download-btn:not(:disabled):hover { opacity: 0.88; }
  .export-error { padding: 8px 10px; background: #fee2e2; color: #991b1b; border-radius: 5px; font-size: 12px; margin-bottom: 10px; }
  .export-warn  { text-align: center; font-size: 11px; color: #f59e0b; margin: 5px 0 0; }

  @media (max-width: 768px) {
    .sidebar-wrapper {
      position: fixed; top: 0; left: 0; height: 100vh;
      transform: translateX(-100%);
      transition: transform 0.25s ease;
      box-shadow: none;
    }
    .sidebar-wrapper.sidebar-open {
      transform: translateX(0);
      box-shadow: 4px 0 24px rgba(0,0,0,0.3);
    }
    .sidebar-overlay {
      display: block; position: fixed; inset: 0;
      background: rgba(0,0,0,0.45); z-index: 199;
    }
    .menu-btn { display: flex; }
    .meta-name { display: none; }
    .tab-btn { padding: 4px 7px; font-size: 11px; }
    .chart-container { height: 280px; }
    .sections-grid { grid-template-columns: 1fr; }
    .format-row { grid-template-columns: 1fr; }
  }

  @media (max-width: 480px) {
    .meta-dim { display: none; }
    .export-btn, .analysis-btn { padding: 3px 6px; font-size: 10px; }
  }
</style>