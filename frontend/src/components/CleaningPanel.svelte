<script lang="ts">
  import { createEventDispatcher } from 'svelte';

  interface DatasetMeta {
    id: string;
    name: string;
    columns: string[];
    numeric_columns: string[];
    categorical_columns: string[];
  }

  interface FillOp {
    column: string;
    method: string;
    value: string;
  }

  interface RenameOp {
    from: string;
    to: string;
  }

  interface ConvertOp {
    column: string;
    dtype: string;
  }

  interface CleanResult {
    id: string;
    total_rows: number;
    total_features: number;
    missing_total: number;
    duplicates: number;
  }

  export let datasetId: string | null = null;
  export let datasetMeta: DatasetMeta | null = null;
  export let apiBase = 'http://127.0.0.1:8000';

  const dispatch = createEventDispatcher();

  // ── State ──
  let loading = false;
  let result: CleanResult | null = null;
  let error = '';
  let log: string[] = [];

  // Operations toggles
  let dropDuplicates = false;
  let dropNullsMode = 'none'; // none | all | columns
  let dropNullsCols: string[] = [];

  let fillOps: FillOp[] = [];
  let dropCols: string[] = [];
  let renameOps: RenameOp[] = [];

  let filterRows = { enabled: false, column: '', operator: '==', value: '' };

  let convertOps: ConvertOp[] = [];

  let saveAsName = '';
  let overwrite = false;

  $: cols = datasetMeta?.columns ?? [];
  $: numericCols = datasetMeta?.numeric_columns ?? [];
  $: categoricalCols = datasetMeta?.categorical_columns ?? [];

  // ── Helpers ──
  function addFillOp(): void {
    fillOps = [...fillOps, { column: cols[0] ?? '', method: 'mean', value: '' }];
  }
  function removeFillOp(i: number): void { fillOps = fillOps.filter((_, idx) => idx !== i); }

  function addRenameOp(): void {
    renameOps = [...renameOps, { from: cols[0] ?? '', to: '' }];
  }
  function removeRenameOp(i: number): void { renameOps = renameOps.filter((_, idx) => idx !== i); }

  function addConvertOp(): void {
    convertOps = [...convertOps, { column: cols[0] ?? '', dtype: 'numeric' }];
  }
  function removeConvertOp(i: number): void { convertOps = convertOps.filter((_, idx) => idx !== i); }

  function toggleDropCol(col: string): void {
    dropCols = dropCols.includes(col) ? dropCols.filter(c => c !== col) : [...dropCols, col];
  }

  function toggleDropNullCol(col: string): void {
    dropNullsCols = dropNullsCols.includes(col) ? dropNullsCols.filter(c => c !== col) : [...dropNullsCols, col];
  }

  async function applyClean(): Promise<void> {
    if (!datasetId) return;
    loading = true; error = ''; result = null; log = [];

    const body: Record<string, any> = {};
    if (dropDuplicates) body.drop_duplicates = true;

    if (dropNullsMode === 'all') body.drop_nulls = 'all';
    else if (dropNullsMode === 'columns' && dropNullsCols.length)
      body.drop_nulls = { columns: dropNullsCols };

    if (fillOps.length) {
      body.fill_nulls = fillOps.map(op => ({
        column: op.column,
        method: op.method,
        ...(op.method === 'value' ? { value: op.value } : {}),
      }));
    }

    if (dropCols.length) body.drop_columns = dropCols;

    if (renameOps.length) {
      body.rename_columns = Object.fromEntries(
        renameOps.filter(r => r.from && r.to).map(r => [r.from, r.to])
      );
    }

    if (filterRows.enabled && filterRows.column) {
      const rawVal: string = filterRows.value;
      const n = Number(rawVal);
      const val: string | number = !isNaN(n) && rawVal !== '' ? n : rawVal;
      body.filter_rows = { column: filterRows.column, operator: filterRows.operator, value: val };
    }

    if (convertOps.length) {
      body.convert_dtype = convertOps.map(op => ({ column: op.column, dtype: op.dtype }));
    }

    body.save_as = saveAsName || undefined;
    body.overwrite = overwrite;

    try {
      const res = await fetch(`${apiBase}/api/v1/clean/${datasetId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
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

  function exportDataset(id: string): void {
    window.open(`${apiBase}/api/v1/export/${id}`, '_blank');
  }

  // UI helpers
  const methodLabels: Record<string, string> = {
    mean: 'Media', median: 'Mediana', mode: 'Moda',
    ffill: 'Forward fill', bfill: 'Backward fill', value: 'Valor fijo',
  };
  const dtypeLabels: Record<string, string> = {
    numeric: 'Numérico', datetime: 'Fecha/Hora', string: 'Texto', category: 'Categoría',
  };
  const operatorLabels = ['==', '!=', '>', '<', '>=', '<=', 'contains'];
</script>

<div style="height: 100%; overflow-y: auto; padding: 20px; max-width: 900px; margin: 0 auto;">
  {#if !datasetId}
    <div style="display: flex; align-items: center; justify-content: center; height: 200px; color: #94a3b8; flex-direction: column; gap: 12px;">
      <span style="font-size: 40px;"></span>
      <p style="margin: 0;">Selecciona un dataset para limpiar.</p>
    </div>
  {:else}
    <h3 style="margin: 0 0 20px; font-size: 16px; color: #0f172a;">
      Limpieza de datos
      <span style="font-weight: 400; font-size: 13px; color: #64748b; margin-left: 8px;">{datasetMeta?.name}</span>
    </h3>

    <!-- ── Drop duplicates ── -->
    <section style={sectionStyle}>
      <label style="display: flex; align-items: center; gap: 10px; cursor: pointer;">
        <input type="checkbox" bind:checked={dropDuplicates} style="width: 16px; height: 16px;" />
        <div>
          <span style="font-size: 14px; font-weight: 600; color: #1e293b;">Eliminar duplicados</span>
          <p style="margin: 2px 0 0; font-size: 12px; color: #94a3b8;">Elimina filas idénticas en todas las columnas.</p>
        </div>
      </label>
    </section>

    <!-- ── Drop nulls ── -->
    <section style={sectionStyle}>
      <p style={sectionTitle}>Eliminar filas con nulos</p>
      <div style="display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 10px;">
        {#each [['none','No eliminar'],['all','Todas las columnas'],['columns','Columnas específicas']] as [val, lbl]}
          <label style="display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 13px; color: #334155;">
            <input type="radio" name="dropNulls" value={val} bind:group={dropNullsMode} />
            {lbl}
          </label>
        {/each}
      </div>
      {#if dropNullsMode === 'columns'}
        <div style="display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px;">
          {#each cols as col}
            <label style="display: flex; align-items: center; gap: 5px; cursor: pointer; font-size: 12px; color: #475569;">
              <input type="checkbox" checked={dropNullsCols.includes(col)} on:change={() => toggleDropNullCol(col)} />
              {col}
            </label>
          {/each}
        </div>
      {/if}
    </section>

    <!-- ── Fill nulls ── -->
    <section style={sectionStyle}>
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
        <p style={sectionTitle}>Rellenar nulos</p>
        <button on:click={addFillOp} style={addBtnStyle}>+ Agregar regla</button>
      </div>
      {#each fillOps as op, i}
        <div style="display: flex; gap: 8px; align-items: center; margin-bottom: 8px; flex-wrap: wrap;">
          <select bind:value={op.column} style={selectStyle}>
            {#each cols as col}<option value={col}>{col}</option>{/each}
          </select>
          <select bind:value={op.method} style={selectStyle}>
            {#each Object.entries(methodLabels) as [v, l]}<option value={v}>{l}</option>{/each}
          </select>
          {#if op.method === 'value'}
            <input bind:value={op.value} placeholder="Valor" style={inputStyle} />
          {/if}
          <button on:click={() => removeFillOp(i)} style={removeBtnStyle}>×</button>
        </div>
      {/each}
    </section>

    <!-- ── Drop columns ── -->
    <section style={sectionStyle}>
      <p style={sectionTitle}>Eliminar columnas</p>
      <div style="display: flex; flex-wrap: wrap; gap: 8px;">
        {#each cols as col}
          <label style="display: flex; align-items: center; gap: 5px; cursor: pointer;">
            <input type="checkbox" checked={dropCols.includes(col)} on:change={() => toggleDropCol(col)} />
            <span style="font-size: 12px; color: #475569; {dropCols.includes(col) ? 'text-decoration: line-through; color: #ef4444;' : ''}">{col}</span>
          </label>
        {/each}
      </div>
    </section>

    <!-- ── Rename columns ── -->
    <section style={sectionStyle}>
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
        <p style={sectionTitle}>Renombrar columnas</p>
        <button on:click={addRenameOp} style={addBtnStyle}>+ Agregar</button>
      </div>
      {#each renameOps as op, i}
        <div style="display: flex; gap: 8px; align-items: center; margin-bottom: 8px;">
          <select bind:value={op.from} style={selectStyle}>
            {#each cols as col}<option value={col}>{col}</option>{/each}
          </select>
          <span style="color: #94a3b8; font-size: 16px;">→</span>
          <input bind:value={op.to} placeholder="Nuevo nombre" style={inputStyle} />
          <button on:click={() => removeRenameOp(i)} style={removeBtnStyle}>×</button>
        </div>
      {/each}
    </section>

    <!-- ── Filter rows ── -->
    <section style={sectionStyle}>
      <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 10px;">
        <label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
          <input type="checkbox" bind:checked={filterRows.enabled} />
          <p style={sectionTitle}>Filtrar filas</p>
        </label>
      </div>
      {#if filterRows.enabled}
        <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
          <select bind:value={filterRows.column} style={selectStyle}>
            {#each cols as col}<option value={col}>{col}</option>{/each}
          </select>
          <select bind:value={filterRows.operator} style={selectStyle}>
            {#each operatorLabels as op}<option value={op}>{op}</option>{/each}
          </select>
          <input bind:value={filterRows.value} placeholder="Valor de comparación" style={inputStyle} />
        </div>
        <p style="margin: 8px 0 0; font-size: 11px; color: #94a3b8;">
          Mantiene las filas donde la condición es verdadera. Usa "contains" para buscar texto parcial.
        </p>
      {/if}
    </section>

    <!-- ── Convert dtypes ── -->
    <section style={sectionStyle}>
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
        <p style={sectionTitle}>Convertir tipos de dato</p>
        <button on:click={addConvertOp} style={addBtnStyle}>+ Agregar</button>
      </div>
      {#each convertOps as op, i}
        <div style="display: flex; gap: 8px; align-items: center; margin-bottom: 8px;">
          <select bind:value={op.column} style={selectStyle}>
            {#each cols as col}<option value={col}>{col}</option>{/each}
          </select>
          <span style="color: #94a3b8;">→</span>
          <select bind:value={op.dtype} style={selectStyle}>
            {#each Object.entries(dtypeLabels) as [v, l]}<option value={v}>{l}</option>{/each}
          </select>
          <button on:click={() => removeConvertOp(i)} style={removeBtnStyle}>×</button>
        </div>
      {/each}
    </section>

    <!-- ── Save options ── -->
    <section style={sectionStyle}>
      <p style={sectionTitle}>Guardar resultado</p>
      <div style="display: flex; gap: 12px; align-items: center; flex-wrap: wrap;">
        <input bind:value={saveAsName} placeholder="Nombre del nuevo dataset (opcional)"
          style="flex: 1; min-width: 200px; {inputStyle}" />
        <label style="display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 13px; color: #475569;">
          <input type="checkbox" bind:checked={overwrite} />
          Sobrescribir dataset original
        </label>
      </div>
    </section>

    <!-- ── Apply button ── -->
    <div style="margin-top: 8px; margin-bottom: 24px; display: flex; gap: 12px; align-items: center;">
      <button on:click={applyClean} disabled={loading} style="
        padding: 11px 28px; background: {loading ? '#94a3b8' : '#0f172a'}; color: white;
        border: none; border-radius: 7px; font-size: 14px; font-weight: 700;
        cursor: {loading ? 'not-allowed' : 'pointer'};
      ">
        {loading ? 'Procesando...' : 'Aplicar Limpieza'}
      </button>
    </div>

    <!-- Error -->
    {#if error}
      <div style="padding: 12px 16px; background: #fee2e2; color: #991b1b; border-radius: 8px; margin-bottom: 16px; font-size: 13px;">
        ⚠ {error}
      </div>
    {/if}

    <!-- Result -->
    {#if result}
      <div style="padding: 16px; background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; margin-bottom: 16px;">
        <p style="margin: 0 0 10px; font-size: 14px; font-weight: 700; color: #166534;">✓ Limpieza aplicada correctamente</p>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; margin-bottom: 12px;">
          {#each [
            { l: 'Filas', v: result.total_rows.toLocaleString() },
            { l: 'Columnas', v: result.total_features },
            { l: 'Nulos', v: result.missing_total },
            { l: 'Duplicados', v: result.duplicates },
          ] as k}
            <div style="background: white; border-radius: 6px; padding: 10px; text-align: center;">
              <div style="font-size: 18px; font-weight: 700; color: #0f172a;">{k.v}</div>
              <div style="font-size: 11px; color: #64748b;">{k.l}</div>
            </div>
          {/each}
        </div>
        {#if log.length}
          <div style="margin-bottom: 12px;">
            <p style="margin: 0 0 6px; font-size: 12px; font-weight: 600; color: #15803d;">Operaciones realizadas:</p>
            {#each log as l}
              <p style="margin: 2px 0; font-size: 12px; color: #166534; padding-left: 12px;">• {l}</p>
            {/each}
          </div>
        {/if}
        <div style="display: flex; gap: 10px;">
          <button on:click={() => dispatch('selectDataset', { id: result!.id })} style="
            padding: 8px 16px; background: #1d4ed8; color: white; border: none;
            border-radius: 6px; font-size: 13px; font-weight: 600; cursor: pointer;
          ">Ver dataset limpio</button>
          <button on:click={() => exportDataset(result!.id)} style="
            padding: 8px 16px; background: white; color: #0f172a; border: 1px solid #e2e8f0;
            border-radius: 6px; font-size: 13px; font-weight: 600; cursor: pointer;
          ">⬇ Descargar CSV</button>
        </div>
      </div>
    {/if}
  {/if}
</div>

<script context="module">
  const sectionStyle = `
    background: white; border: 1px solid #e2e8f0; border-radius: 8px;
    padding: 16px; margin-bottom: 14px;
  `;
  const sectionTitle = `margin: 0 0 0; font-size: 14px; font-weight: 600; color: #334155;`;
  const addBtnStyle = `
    padding: 5px 12px; background: #eff6ff; color: #1d4ed8;
    border: 1px solid #bfdbfe; border-radius: 5px; font-size: 12px;
    font-weight: 600; cursor: pointer;
  `;
  const removeBtnStyle = `
    padding: 4px 10px; background: #fee2e2; color: #ef4444;
    border: 1px solid #fecaca; border-radius: 5px; font-size: 14px;
    cursor: pointer;
  `;
  const selectStyle = `
    padding: 6px 10px; border: 1px solid #e2e8f0; border-radius: 6px;
    font-size: 12px; color: #334155; background: white; cursor: pointer;
  `;
  const inputStyle = `
    padding: 6px 10px; border: 1px solid #e2e8f0; border-radius: 6px;
    font-size: 12px; color: #334155; outline: none;
  `;
</script>