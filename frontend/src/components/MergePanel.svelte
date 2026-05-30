<script lang="ts">
  import { createEventDispatcher } from 'svelte';

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

  interface MergeResult {
    new_dataset_id: string;
    rows_before: { left: number; right: number };
    rows_after: number;
    result: { total_features: number };
  }

  interface MergeBody {
    left_id: string;
    right_id: string;
    how: string;
    save_as: string;
    on?: string;
    left_on?: string;
    right_on?: string;
  }

  export let datasets: Dataset[] = [];
  export let apiBase = 'http://127.0.0.1:8000';

  const dispatch = createEventDispatcher();

  let leftId = '';
  let rightId = '';
  let howJoin = 'inner';
  let joinMode = 'on';      // on | left_right
  let onCol = '';
  let leftOnCol = '';
  let rightOnCol = '';
  let saveAsName = '';
  let loading = false;
  let result: MergeResult | null = null;
  let error = '';

  $: leftMeta = datasets.find((d: Dataset) => d.id === leftId);
  $: rightMeta = datasets.find((d: Dataset) => d.id === rightId);
  $: leftCols = leftMeta?.columns ?? [];
  $: rightCols = rightMeta?.columns ?? [];
  $: sharedCols = leftCols.filter((c: string) => rightCols.includes(c));

  // Reset join column when datasets change
  $: if (sharedCols.length) onCol = sharedCols[0];

  const joinTypes = [
    { val: 'inner', label: 'INNER', desc: 'Solo filas con coincidencia en ambos lados' },
    { val: 'left', label: 'LEFT', desc: 'Todas las filas del dataset izquierdo' },
    { val: 'right', label: 'RIGHT', desc: 'Todas las filas del dataset derecho' },
    { val: 'outer', label: 'OUTER', desc: 'Todas las filas de ambos datasets' },
  ];

  async function executeMerge(): Promise<void> {
    if (!leftId || !rightId) return;
    loading = true; error = ''; result = null;

    const body: MergeBody = {
      left_id: leftId,
      right_id: rightId,
      how: howJoin,
      save_as: saveAsName || `${leftMeta?.name?.replace('.csv','')}_${rightMeta?.name?.replace('.csv','')}`,
    };

    if (joinMode === 'on') {
      body.on = onCol;
    } else {
      body.left_on = leftOnCol;
      body.right_on = rightOnCol;
    }

    try {
      const res = await fetch(`${apiBase}/api/v1/merge`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) { const d = await res.json(); throw new Error(d.detail); }
      const data = await res.json();
      result = data;
      dispatch('refresh');
    } catch (e) {
      error = String(e);
    } finally {
      loading = false;
    }
  }

  function exportDataset(id: string): void {
    window.open(`${apiBase}/api/v1/export/${id}`, '_blank');
  }

  function getLossLabel(val: number): string {
    if (howJoin === 'inner') return `${((1 - val) * 100).toFixed(1)}% descartado`;
    return '';
  }
</script>

<div style="height: 100%; overflow-y: auto; padding: 20px; max-width: 800px; margin: 0 auto;">
  <h3 style="margin: 0 0 6px; font-size: 16px; color: #0f172a;">Combinar Datasets (Merge / Join)</h3>
  <p style="margin: 0 0 20px; font-size: 13px; color: #64748b;">
    Combina dos datasets usando una columna clave común, similar a un JOIN de SQL.
  </p>

  {#if datasets.length < 2}
    <div style="padding: 24px; background: #f8fafc; border: 1px dashed #cbd5e1; border-radius: 8px; text-align: center; color: #94a3b8;">
      Necesitas al menos <strong>2 datasets cargados</strong> para hacer un merge.
    </div>
  {:else}
    <!-- Dataset selection -->
    <div style="display: grid; grid-template-columns: 1fr 60px 1fr; gap: 12px; align-items: start; margin-bottom: 20px;">
      <!-- Left -->
      <div style="background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px;">
        <p style="margin: 0 0 10px; font-size: 12px; font-weight: 600; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px;">
          Dataset Izquierdo
        </p>
        <select bind:value={leftId} style="width: 100%; padding: 8px 10px; border: 1px solid #e2e8f0; border-radius: 6px; font-size: 13px; color: #334155; margin-bottom: 10px;">
          <option value="">— Seleccionar —</option>
          {#each datasets as ds}
            <option value={ds.id}>{ds.name}</option>
          {/each}
        </select>
        {#if leftMeta}
          <div style="font-size: 11px; color: #64748b;">
            <span>{leftMeta.total_rows.toLocaleString()} filas</span> ·
            <span>{leftMeta.total_features} cols</span>
          </div>
          <div style="margin-top: 8px; max-height: 100px; overflow-y: auto;">
            {#each leftCols as col}
              <span style="display: inline-block; margin: 2px; padding: 2px 6px; background: #f1f5f9; border-radius: 4px; font-size: 10px; color: #475569;">
                {col}
              </span>
            {/each}
          </div>
        {/if}
      </div>

      <!-- Join icon -->
      <div style="display: flex; align-items: center; justify-content: center; height: 80px; margin-top: 32px;">
        <div style="font-size: 24px; text-align: center;">
          <div>⋈</div>
          <div style="font-size: 10px; color: #94a3b8; font-weight: 700; margin-top: 4px;">{howJoin.toUpperCase()}</div>
        </div>
      </div>

      <!-- Right -->
      <div style="background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px;">
        <p style="margin: 0 0 10px; font-size: 12px; font-weight: 600; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px;">
          Dataset Derecho
        </p>
        <select bind:value={rightId} style="width: 100%; padding: 8px 10px; border: 1px solid #e2e8f0; border-radius: 6px; font-size: 13px; color: #334155; margin-bottom: 10px;">
          <option value="">— Seleccionar —</option>
          {#each datasets.filter((d: Dataset) => d.id !== leftId) as ds}
            <option value={ds.id}>{ds.name}</option>
          {/each}
        </select>
        {#if rightMeta}
          <div style="font-size: 11px; color: #64748b;">
            <span>{rightMeta.total_rows.toLocaleString()} filas</span> ·
            <span>{rightMeta.total_features} cols</span>
          </div>
          <div style="margin-top: 8px; max-height: 100px; overflow-y: auto;">
            {#each rightCols as col}
              <span style="display: inline-block; margin: 2px; padding: 2px 6px; background: {sharedCols.includes(col) ? '#dbeafe' : '#f1f5f9'}; border-radius: 4px; font-size: 10px; color: {sharedCols.includes(col) ? '#1d4ed8' : '#475569'};">
                {col}
              </span>
            {/each}
          </div>
          {#if sharedCols.length}
            <p style="margin: 8px 0 0; font-size: 10px; color: #1d4ed8;">🔵 Columnas compartidas resaltadas</p>
          {/if}
        {/if}
      </div>
    </div>

    {#if leftId && rightId}
      <!-- Join type -->
      <div style="background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin-bottom: 14px;">
        <p style="margin: 0 0 12px; font-size: 14px; font-weight: 600; color: #334155;">Tipo de JOIN</p>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 10px;">
          {#each joinTypes as jt}
            <!-- svelte-ignore a11y-click-events-have-key-events -->
            <!-- svelte-ignore a11y-no-static-element-interactions -->
            <div
              on:click={() => howJoin = jt.val}
              style="
                padding: 12px; border-radius: 7px; cursor: pointer; text-align: center;
                border: 2px solid {howJoin === jt.val ? '#3b82f6' : '#e2e8f0'};
                background: {howJoin === jt.val ? '#eff6ff' : 'white'};
              "
            >
              <p style="margin: 0 0 4px; font-size: 13px; font-weight: 700; color: {howJoin === jt.val ? '#1d4ed8' : '#334155'};">
                {jt.label}
              </p>
              <p style="margin: 0; font-size: 11px; color: #64748b; line-height: 1.4;">{jt.desc}</p>
            </div>
          {/each}
        </div>
      </div>

      <!-- Join columns -->
      <div style="background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin-bottom: 14px;">
        <p style="margin: 0 0 12px; font-size: 14px; font-weight: 600; color: #334155;">Columna de unión</p>
        <div style="display: flex; gap: 16px; margin-bottom: 12px;">
          <label style="display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 13px; color: #334155;">
            <input type="radio" name="joinMode" value="on" bind:group={joinMode} />
            Misma columna en ambos
          </label>
          <label style="display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 13px; color: #334155;">
            <input type="radio" name="joinMode" value="left_right" bind:group={joinMode} />
            Columnas distintas
          </label>
        </div>

        {#if joinMode === 'on'}
          <div style="display: flex; align-items: center; gap: 8px;">
            <select bind:value={onCol} style="padding: 8px 10px; border: 1px solid #e2e8f0; border-radius: 6px; font-size: 13px; color: #334155; min-width: 200px;">
              {#each [...new Set([...leftCols, ...rightCols])] as col}
                <option value={col} style="color: {sharedCols.includes(col) ? '#1d4ed8' : '#334155'};">
                  {col} {sharedCols.includes(col) ? '✓' : ''}
                </option>
              {/each}
            </select>
            {#if !sharedCols.includes(onCol)}
              <span style="font-size: 11px; color: #f59e0b; background: #fef3c7; padding: 4px 8px; border-radius: 4px;">
                ⚠ Esta columna no existe en ambos datasets
              </span>
            {/if}
          </div>
        {:else}
          <div style="display: flex; align-items: center; gap: 12px; flex-wrap: wrap;">
            <div>
              <label for="left-on-col" style="display: block; font-size: 11px; color: #64748b; margin-bottom: 4px;">Columna izquierda</label>
              <select id="left-on-col" bind:value={leftOnCol} style="padding: 7px 10px; border: 1px solid #e2e8f0; border-radius: 6px; font-size: 13px; color: #334155;">
                {#each leftCols as col}<option value={col}>{col}</option>{/each}
              </select>
            </div>
            <span style="color: #94a3b8; font-size: 18px; margin-top: 16px;">=</span>
            <div>
              <label for="right-on-col" style="display: block; font-size: 11px; color: #64748b; margin-bottom: 4px;">Columna derecha</label>
              <select id="right-on-col" bind:value={rightOnCol} style="padding: 7px 10px; border: 1px solid #e2e8f0; border-radius: 6px; font-size: 13px; color: #334155;">
                {#each rightCols as col}<option value={col}>{col}</option>{/each}
              </select>
            </div>
          </div>
        {/if}
      </div>

      <!-- Save as -->
      <div style="background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin-bottom: 20px;">
        <p style="margin: 0 0 10px; font-size: 14px; font-weight: 600; color: #334155;">Nombre del resultado</p>
        <input bind:value={saveAsName} placeholder="ej. ventas_con_productos" style="
          width: 100%; padding: 8px 12px; border: 1px solid #e2e8f0; border-radius: 6px;
          font-size: 13px; color: #334155; box-sizing: border-box;
        " />
      </div>

      <!-- Execute -->
      <button on:click={executeMerge} disabled={loading || !leftId || !rightId} style="
        padding: 12px 32px; background: {loading ? '#94a3b8' : '#0f172a'}; color: white;
        border: none; border-radius: 7px; font-size: 14px; font-weight: 700; cursor: pointer;
        margin-bottom: 20px;
      ">
        {loading ? 'Combinando...' : '⋈ Ejecutar Merge'}
      </button>
    {/if}

    <!-- Error -->
    {#if error}
      <div style="padding: 12px 16px; background: #fee2e2; color: #991b1b; border-radius: 8px; margin-bottom: 16px; font-size: 13px;">
        ⚠ {error}
      </div>
    {/if}

    <!-- Result -->
    {#if result}
      <div style="padding: 16px; background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px;">
        <p style="margin: 0 0 12px; font-size: 14px; font-weight: 700; color: #166534;">✓ Merge completado</p>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; margin-bottom: 14px;">
          {#each [
            { l: 'Filas izquierda', v: result.rows_before.left.toLocaleString() },
            { l: 'Filas derecha', v: result.rows_before.right.toLocaleString() },
            { l: 'Filas resultado', v: result.rows_after.toLocaleString() },
            { l: 'Columnas', v: result.result.total_features },
          ] as k}
            <div style="background: white; border-radius: 6px; padding: 10px; text-align: center;">
              <div style="font-size: 18px; font-weight: 700; color: #0f172a;">{k.v}</div>
              <div style="font-size: 11px; color: #64748b;">{k.l}</div>
            </div>
          {/each}
        </div>
        <div style="display: flex; gap: 10px;">
          <button on:click={() => dispatch('selectDataset', { id: result!.new_dataset_id })} style="
            padding: 8px 16px; background: #1d4ed8; color: white; border: none;
            border-radius: 6px; font-size: 13px; font-weight: 600; cursor: pointer;
          ">Ver dataset combinado</button>
          <button on:click={() => exportDataset(result!.new_dataset_id)} style="
            padding: 8px 16px; background: white; color: #0f172a; border: 1px solid #e2e8f0;
            border-radius: 6px; font-size: 13px; font-weight: 600; cursor: pointer;
          ">⬇ Descargar CSV</button>
        </div>
      </div>
    {/if}
  {/if}
</div>