<script lang="ts">
  import { onMount, afterUpdate } from "svelte";
  import * as echarts from "echarts";
  import type { ECharts } from "echarts";
  import './styles/EdaPanel.css';

  interface MissingInfo {
    column: string;
    missing: number;
    pct: number;
  }

  interface NumericStat {
    column: string;
    count: number;
    nulls: number;
    mean: number;
    median: number;
    std: number;
    min: number;
    max: number;
    q25: number;
    q75: number;
    skewness: number;
    kurtosis: number;
  }

  interface CategoricalStat {
    column: string;
    unique: number;
    nulls: number;
    top_10: { name: string; value: number }[];
  }

  interface Distribution {
    bins: number[];
    counts: number[];
  }

  interface EdaData {
    name: string;
    shape: { rows: number; cols: number };
    duplicates: number;
    columns: string[];
    dtypes: Record<string, string>;
    missing_data: MissingInfo[];
    numeric_stats: NumericStat[];
    categorical_stats: CategoricalStat[];
    distributions: Record<string, Distribution>;
    correlation: { columns: string[]; matrix: number[][] } | null;
    sample_data: Record<string, any>[];
  }

  export let datasetId: string | null = null;
  export let apiBase = "http://127.0.0.1:8000";

  let eda: EdaData | null = null;
  let loading = false;
  let error = "";
  let activeSection = "overview";

  let corrContainer: HTMLDivElement | null = null;
  let corrChart: ECharts | null = null;

  let histContainers: Record<string, HTMLDivElement> = {};
  let histCharts: Record<string, ECharts> = {};

  $: if (datasetId) loadEda(datasetId);

  async function loadEda(id: string): Promise<void> {
    loading = true;
    error = "";
    eda = null;
    destroyCharts();
    try {
      const res = await fetch(`${apiBase}/api/v1/eda/${id}`);
      if (!res.ok) {
        const d = await res.json();
        throw new Error(d.detail);
      }
      eda = await res.json();
    } catch (e) {
      error = String(e);
    } finally {
      loading = false;
    }
  }

  function destroyCharts(): void {
    if (corrChart) {
      corrChart.dispose();
      corrChart = null;
    }
    Object.values(histCharts).forEach((c) => c.dispose());
    histCharts = {};
  }

  afterUpdate(() => {
    if (!eda) return;

    const correlation = eda.correlation;
    if (corrContainer && !corrChart && correlation && correlation.columns.length > 1) {
      corrChart = echarts.init(corrContainer);
      const cols = correlation.columns;
      const matrix = correlation.matrix;
      const data: [number, number, number][] = [];
      for (let i = 0; i < cols.length; i++)
        for (let j = 0; j < cols.length; j++)
          data.push([i, j, matrix[i][j]]);

      corrChart.setOption({
        tooltip: { formatter: (p: any) => `${cols[p.value[1]]} / ${cols[p.value[0]]}<br/>${p.value[2]}` },
        grid: { top: 10, bottom: 60, left: 100, right: 20 },
        xAxis: { type: 'category', data: cols, axisLabel: { rotate: 45, fontSize: 11 } },
        yAxis: { type: 'category', data: cols, axisLabel: { fontSize: 11 } },
        visualMap: {
          min: -1, max: 1, calculable: true, orient: 'horizontal',
          left: 'center', bottom: 0, inRange: { color: ['#3b82f6', '#f8fafc', '#ef4444'] },
        },
        series: [{
          type: 'heatmap', data,
          label: { show: cols.length <= 8, fontSize: 10 },
          emphasis: { itemStyle: { shadowBlur: 10 } },
        }],
      });
    }

    if (eda.distributions) {
      for (const [col, dist] of Object.entries(eda.distributions)) {
        const container = histContainers[col];
        if (container && !histCharts[col]) {
          const chart = echarts.init(container);
          const labels: string[] = dist.bins
            .slice(0, -1)
            .map(
              (b: number, i: number) =>
                `${b.toFixed(2)}–${dist.bins[i + 1].toFixed(2)}`,
            );
          chart.setOption({
            tooltip: { trigger: "axis" },
            grid: { top: 10, bottom: 40, left: 45, right: 10 },
            xAxis: {
              type: "category",
              data: labels,
              axisLabel: { rotate: 45, fontSize: 9, interval: 4 },
            },
            yAxis: { type: "value", axisLabel: { fontSize: 10 } },
            series: [
              {
                type: "bar",
                data: dist.counts,
                itemStyle: { color: "#3b82f6", borderRadius: [2, 2, 0, 0] },
              },
            ],
          });
          histCharts[col] = chart;
        }
      }
    }
  });

  function missingPctColor(pct: number): string {
    if (pct === 0) return "#10b981";
    if (pct < 5) return "#f59e0b";
    if (pct < 20) return "#f97316";
    return "#ef4444";
  }

  const tabs = [
    { id: "overview", label: "Resumen" },
    { id: "numeric", label: "Numerico" },
    { id: "categorical", label: "Categorico" },
    { id: "correlation", label: "Correlacion" },
    { id: "sample", label: "Muestra" },
  ];
</script>

<div
  style="height: 100%; display: flex; flex-direction: column; overflow: hidden;"
>
  {#if !datasetId}
    <div
      style="flex: 1; display: flex; align-items: center; justify-content: center; color: #94a3b8; flex-direction: column; gap: 12px;"
    >
      <p style="margin: 0; font-size: 15px;">
        Selecciona un dataset en el panel izquierdo.
      </p>
    </div>
  {:else if loading}
    <div
      style="flex: 1; display: flex; align-items: center; justify-content: center; color: #94a3b8; flex-direction: column; gap: 12px;"
    >
      <div
        style="width: 36px; height: 36px; border: 3px solid #3b82f6; border-top-color: transparent; border-radius: 50%; animation: spin 0.8s linear infinite;"
      ></div>
      <p style="margin: 0; font-size: 14px;">Analizando dataset...</p>
    </div>
  {:else if error}
    <div
      style="margin: 20px; padding: 14px; background: #fee2e2; color: #991b1b; border-radius: 8px;"
    >
      {error}
    </div>
  {:else if eda}
    <div
      style="display: flex; gap: 4px; padding: 12px 16px; background: #f8fafc; border-bottom: 1px solid #e2e8f0; flex-shrink: 0; overflow-x: auto;"
    >
      {#each tabs as tab}
        <button
          on:click={() => (activeSection = tab.id)}
          style="
            padding: 6px 14px; border-radius: 6px; border: 1px solid {activeSection ===
          tab.id
            ? '#3b82f6'
            : '#e2e8f0'};
            background: {activeSection === tab.id
            ? '#eff6ff'
            : 'white'}; color: {activeSection === tab.id
            ? '#1d4ed8'
            : '#64748b'};
            font-size: 13px; font-weight: {activeSection === tab.id
            ? '600'
            : '400'}; cursor: pointer; white-space: nowrap;
          ">{tab.label}</button
        >
      {/each}
    </div>

    <div style="flex: 1; overflow-y: auto; padding: 20px;">
      {#if activeSection === "overview"}
        <h3 style="margin: 0 0 16px; font-size: 16px; color: #0f172a;">
          {eda.name}
        </h3>

        <div
          style="display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin-bottom: 24px;"
        >
          {#each [{ label: "Filas", val: eda.shape.rows.toLocaleString(), warn: false }, { label: "Columnas", val: eda.shape.cols, warn: false }, { label: "Duplicados", val: eda.duplicates, warn: eda.duplicates > 0 }, { label: "Valores Nulos", val: eda.missing_data
                .reduce((s: number, m: MissingInfo) => s + m.missing, 0)
                .toLocaleString(), warn: eda.missing_data.length > 0 }] as kpi}
            <div
              style="background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px;"
            >
              <div
                style="font-size: 22px; font-weight: 700; color: {kpi.warn
                  ? '#d97706'
                  : '#0f172a'};"
              >
                {kpi.val}
              </div>
              <div style="font-size: 12px; color: #64748b;">{kpi.label}</div>
            </div>
          {/each}
        </div>

        <h4 style="margin: 0 0 10px; font-size: 14px; color: #334155;">
          Columnas ({eda.columns.length})
        </h4>
        <div
          style="background: white; border: 1px solid #e2e8f0; border-radius: 8px; overflow: auto; margin-bottom: 24px;"
        >
          <table
            style="width: 100%; border-collapse: collapse; font-size: 13px;"
          >
            <thead>
              <tr style="background: #f8fafc;">
                <th style="padding: 10px 12px; text-align: left; color: #64748b; font-weight: 600; border-bottom: 1px solid #e2e8f0;">Columna</th>
                <th style="padding: 10px 12px; text-align: left; color: #64748b; font-weight: 600; border-bottom: 1px solid #e2e8f0;">Tipo</th>
                <th style="padding: 10px 12px; text-align: right; color: #64748b; font-weight: 600; border-bottom: 1px solid #e2e8f0;">Nulos</th>
                <th style="padding: 10px 12px; text-align: left; color: #64748b; font-weight: 600; border-bottom: 1px solid #e2e8f0;">% Nulos</th>
              </tr>
            </thead>
            <tbody>
              {#each eda.columns as col}
                {@const minfo = eda.missing_data.find((m: MissingInfo) => m.column === col)}
                <tr style="border-bottom: 1px solid #f1f5f9;">
                  <td style="padding: 8px 12px; font-weight: 500; color: #1e293b;">{col}</td>
                  <td style="padding: 8px 12px; color: #64748b;">
                    <span style="background: #f1f5f9; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-family: monospace;">
                      {eda.dtypes[col]}
                    </span>
                  </td>
                  <td style="padding: 8px 12px; text-align: right; color: {minfo ? '#d97706' : '#10b981'}; font-weight: 600;">
                    {minfo ? minfo.missing : 0}
                  </td>
                  <td style="padding: 8px 12px;">
                    <div style="display: flex; align-items: center; gap: 8px;">
                      <div style="flex: 1; background: #f1f5f9; border-radius: 999px; height: 6px; max-width: 120px;">
                        <div style="width: {minfo ? minfo.pct : 0}%; height: 100%; border-radius: 999px; background: {missingPctColor(minfo?.pct ?? 0)};"></div>
                      </div>
                      <span style="font-size: 11px; color: #64748b; min-width: 36px;">{minfo ? minfo.pct + "%" : "0%"}</span>
                    </div>
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>

      {:else if activeSection === "numeric"}
        {#if eda.numeric_stats.length === 0}
          <p style="color: #64748b;">No hay columnas numericas en este dataset.</p>
        {:else}
          <div style="background: white; border: 1px solid #e2e8f0; border-radius: 8px; overflow: auto; margin-bottom: 24px;">
            <table style="width: 100%; border-collapse: collapse; font-size: 12px;">
              <thead>
                <tr style="background: #f8fafc;">
                  {#each ["Columna", "Cnt", "Nulos", "Media", "Mediana", "Std", "Min", "Max", "Q25", "Q75", "Asimetria", "Curtosis"] as h}
                    <th style="padding: 10px 10px; text-align: right; color: #64748b; font-weight: 600; border-bottom: 1px solid #e2e8f0; white-space: nowrap;">{h}</th>
                  {/each}
                </tr>
              </thead>
              <tbody>
                {#each eda.numeric_stats as s}
                  <tr style="border-bottom: 1px solid #f1f5f9;">
                    <td style="padding: 8px 10px; font-weight: 600; color: #1e293b; white-space: nowrap;">{s.column}</td>
                    <td style="padding: 8px 10px; text-align: right; color: #64748b;">{s.count.toLocaleString()}</td>
                    <td style="padding: 8px 10px; text-align: right; color: {s.nulls > 0 ? '#d97706' : '#10b981'}; font-weight: 600;">{s.nulls}</td>
                    <td style="padding: 8px 10px; text-align: right;">{s.mean}</td>
                    <td style="padding: 8px 10px; text-align: right;">{s.median}</td>
                    <td style="padding: 8px 10px; text-align: right;">{s.std}</td>
                    <td style="padding: 8px 10px; text-align: right; color: #3b82f6;">{s.min}</td>
                    <td style="padding: 8px 10px; text-align: right; color: #3b82f6;">{s.max}</td>
                    <td style="padding: 8px 10px; text-align: right; color: #64748b;">{s.q25}</td>
                    <td style="padding: 8px 10px; text-align: right; color: #64748b;">{s.q75}</td>
                    <td style="padding: 8px 10px; text-align: right; color: {Math.abs(s.skewness) > 1 ? '#f59e0b' : '#64748b'};">{s.skewness}</td>
                    <td style="padding: 8px 10px; text-align: right; color: #64748b;">{s.kurtosis}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>

          <h4 style="margin: 0 0 14px; font-size: 14px; color: #334155;">Distribuciones</h4>
          <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 16px;">
            {#each Object.keys(eda.distributions) as col}
              <div style="background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px;">
                <p style="margin: 0 0 8px; font-size: 12px; font-weight: 600; color: #334155;">{col}</p>
                <div bind:this={histContainers[col]} style="height: 160px;"></div>
              </div>
            {/each}
          </div>
        {/if}

      {:else if activeSection === "categorical"}
        {#if eda.categorical_stats.length === 0}
          <p style="color: #64748b;">No hay columnas categoricas en este dataset.</p>
        {:else}
          <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px;">
            {#each eda.categorical_stats as cs}
              <div style="background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px;">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 10px;">
                  <p style="margin: 0; font-size: 13px; font-weight: 700; color: #1e293b;">{cs.column}</p>
                  <div style="display: flex; gap: 8px;">
                    <span style="font-size: 11px; background: #eff6ff; color: #1d4ed8; padding: 2px 7px; border-radius: 12px;">{cs.unique} unicos</span>
                    {#if cs.nulls > 0}
                      <span style="font-size: 11px; background: #fef3c7; color: #92400e; padding: 2px 7px; border-radius: 12px;">{cs.nulls} nulos</span>
                    {/if}
                  </div>
                </div>
                {#each cs.top_10.slice(0, 8) as item}
                  {@const maxVal = cs.top_10[0].value}
                  <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 5px;">
                    <span style="font-size: 11px; color: #334155; width: 110px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex-shrink: 0;" title={item.name}>
                      {item.name}
                    </span>
                    <div style="flex: 1; background: #f1f5f9; border-radius: 999px; height: 8px;">
                      <div style="width: {((item.value / maxVal) * 100).toFixed(1)}%; height: 100%; border-radius: 999px; background: #3b82f6;"></div>
                    </div>
                    <span style="font-size: 11px; color: #64748b; min-width: 40px; text-align: right;">{item.value.toLocaleString()}</span>
                  </div>
                {/each}
              </div>
            {/each}
          </div>
        {/if}

      {:else if activeSection === "correlation"}
        {#if !eda.correlation?.columns?.length || eda.correlation.columns.length < 2}
          <p style="color: #64748b;">Se necesitan al menos 2 columnas numericas para calcular correlaciones.</p>
        {:else}
          <h4 style="margin: 0 0 12px; font-size: 14px; color: #334155;">Matriz de Correlacion de Pearson</h4>
          <div style="background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px;">
            <div bind:this={corrContainer} style="height: {Math.max(300, eda.correlation.columns.length * 40 + 80)}px;"></div>
          </div>
          <p style="margin-top: 12px; font-size: 12px; color: #64748b;">
            Rojo = correlacion positiva fuerte · Azul = correlacion negativa · Blanco = sin correlacion
          </p>
        {/if}

      {:else if activeSection === "sample"}
        <h4 style="margin: 0 0 12px; font-size: 14px; color: #334155;">Muestra de datos (primeras 15 filas)</h4>
        <div style="background: white; border: 1px solid #e2e8f0; border-radius: 8px; overflow: auto;">
          <table style="border-collapse: collapse; font-size: 12px; white-space: nowrap;">
            <thead>
              <tr style="background: #f8fafc;">
                {#each eda.columns as col}
                  <th style="padding: 9px 12px; text-align: left; color: #64748b; font-weight: 600; border-bottom: 1px solid #e2e8f0;">{col}</th>
                {/each}
              </tr>
            </thead>
            <tbody>
              {#each eda.sample_data as row, i}
                <tr style="background: {i % 2 === 0 ? 'white' : '#f8fafc'}; border-bottom: 1px solid #f1f5f9;">
                  {#each eda.columns as col}
                    <td style="padding: 7px 12px; color: #334155; max-width: 200px; overflow: hidden; text-overflow: ellipsis;" title={row[col]}>
                      {row[col]}
                    </td>
                  {/each}
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      {/if}
    </div>
  {/if}
</div>