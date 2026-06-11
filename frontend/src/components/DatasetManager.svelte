<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import './styles/DatasetManager.css';

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

  export let datasets: Dataset[] = [];
  export let selectedId: string | null = null;
  export let apiBase = 'http://127.0.0.1:8000';

  const dispatch = createEventDispatcher();

  // ── Engine selection ──────────────────────────────────────────────
  type Engine = 'pandas' | 'polars';
  let engine: Engine = 'pandas';

  const ENGINE_OPTIONS: { value: Engine; label: string; desc: string }[] = [
    { value: 'pandas', label: 'Pandas',  desc: 'Compatible, estable, ideal para datasets pequeños y medianos' },
    { value: 'polars', label: 'Polars',  desc: 'Más rápido en archivos grandes' },
  ];

  // ── Upload state ───────────────────────────────────────────────────
  let csvFiles: File[] = [];
  let archiveFile: File | null = null;
  let archiveId: string | null = null;
  let archiveCsvList: string[] = [];
  let selectedArchiveCsvs: string[] = [];
  let loadingCsv = false;
  let loadingArchive = false;
  let loadingExtract = false;
  let error = '';
  let successMsg = '';

  let csvInput: HTMLInputElement | null = null;
  let archiveInput: HTMLInputElement | null = null;

  function showSuccess(msg: string): void {
    successMsg = msg;
    setTimeout(() => (successMsg = ''), 3000);
  }

  async function uploadCsvs(): Promise<void> {
    if (!csvInput?.files?.length) return;
    loadingCsv = true;
    error = '';
    const form = new FormData();
    for (const f of csvInput.files) form.append('files', f);
    form.append('engine', engine);
    try {
      const res = await fetch(`${apiBase}/api/v1/upload-csv`, { method: 'POST', body: form });
      const data = await res.json();
      if (data.errors?.length) error = data.errors.map((e: any) => `${e.name}: ${e.error}`).join(' | ');
      if (data.loaded?.length) {
        showSuccess(`${data.loaded.length} dataset(s) cargados con ${engineLabel(data.engine)}.`);
        dispatch('refresh');
      }
    } catch (e) {
      error = String(e);
    } finally {
      loadingCsv = false;
      if (csvInput) csvInput.value = '';
    }
  }

  async function uploadArchive(): Promise<void> {
    if (!archiveInput?.files?.[0]) return;
    loadingArchive = true;
    error = '';
    archiveId = null;
    archiveCsvList = [];
    selectedArchiveCsvs = [];
    const form = new FormData();
    form.append('file', archiveInput.files[0]);
    try {
      const res = await fetch(`${apiBase}/api/v1/upload-archive`, { method: 'POST', body: form });
      if (!res.ok) { const d = await res.json(); throw new Error(d.detail); }
      const data = await res.json();
      archiveId = data.archive_id;
      archiveCsvList = data.files;
      if (!archiveCsvList.length) error = 'El archivo comprimido no contiene CSVs.';
    } catch (e) {
      error = String(e);
    } finally {
      loadingArchive = false;
    }
  }

  function toggleArchiveCsv(fname: string): void {
    selectedArchiveCsvs = selectedArchiveCsvs.includes(fname)
      ? selectedArchiveCsvs.filter(f => f !== fname)
      : [...selectedArchiveCsvs, fname];
  }

  function selectAllArchive(): void {
    selectedArchiveCsvs = selectedArchiveCsvs.length === archiveCsvList.length
      ? []
      : [...archiveCsvList];
  }

  async function extractSelected(): Promise<void> {
    if (!selectedArchiveCsvs.length || !archiveId) return;
    loadingExtract = true;
    error = '';
    const form = new FormData();
    form.append('archive_id', archiveId);
    form.append('selected_files', JSON.stringify(selectedArchiveCsvs));
    form.append('engine', engine);
    try {
      const res = await fetch(`${apiBase}/api/v1/extract-from-archive`, { method: 'POST', body: form });
      const data = await res.json();
      if (data.errors?.length) error = data.errors.map((e: any) => `${e.name}: ${e.error}`).join(' | ');
      if (data.loaded?.length) {
        showSuccess(`${data.loaded.length} archivo(s) extraidos y cargados con ${engineLabel(data.engine)}.`);
        archiveId = null; archiveCsvList = []; selectedArchiveCsvs = [];
        if (archiveInput) archiveInput.value = '';
        dispatch('refresh');
      }
    } catch (e) {
      error = String(e);
    } finally {
      loadingExtract = false;
    }
  }

  async function removeDataset(id: string): Promise<void> {
    await fetch(`${apiBase}/api/v1/datasets/${id}`, { method: 'DELETE' });
    if (selectedId === id) dispatch('select', { id: null });
    dispatch('refresh');
  }

  function fmtBytes(kb: number): string {
    return kb < 1024 ? `${kb} KB` : `${(kb / 1024).toFixed(1)} MB`;
  }

  function engineLabel(e: string): string {
    return e === 'polars' ? 'Polars' : 'Pandas';
  }
</script>

<aside class="sidebar">
  <!-- Header -->
  <div class="sidebar-header">
    <h2 class="sidebar-title">Data Analyzer</h2>
    <p class="sidebar-subtitle">v2.0 — multi-dataset</p>
  </div>

  <!-- Engine Selector -->
  <div class="sidebar-section">
    <p class="section-label">Motor de lectura</p>
    <div class="engine-toggle">
      {#each ENGINE_OPTIONS as opt}
        <button
          class="engine-btn"
          class:engine-btn-active={engine === opt.value}
          on:click={() => (engine = opt.value)}
          title={opt.desc}
        >
          {opt.label}
        </button>
      {/each}
    </div>
    <p class="engine-desc">
      {ENGINE_OPTIONS.find(o => o.value === engine)?.desc ?? ''}
    </p>
  </div>

  <!-- Upload CSV -->
  <div class="sidebar-section">
    <p class="section-label">Cargar CSV(s)</p>
    <input type="file" accept=".csv" multiple bind:this={csvInput}
      on:change={uploadCsvs} class="hidden-input" id="csv-upload" />
    <label for="csv-upload" class="upload-btn upload-btn-blue">
      {loadingCsv ? 'Cargando...' : '+ Seleccionar CSV(s)'}
    </label>
  </div>

  <!-- Upload Archive -->
  <div class="sidebar-section">
    <p class="section-label">Cargar ZIP / RAR</p>
    <input type="file" accept=".zip,.rar" bind:this={archiveInput}
      on:change={uploadArchive} class="hidden-input" id="archive-upload" />
    <label for="archive-upload" class="upload-btn upload-btn-purple">
      {loadingArchive ? 'Leyendo...' : '+ Archivo Comprimido'}
    </label>

    {#if archiveCsvList.length > 0}
      <div class="archive-picker">
        <div class="archive-picker-header">
          <span class="muted-small">{archiveCsvList.length} CSVs encontrados</span>
          <button class="tiny-btn" on:click={selectAllArchive}>
            {selectedArchiveCsvs.length === archiveCsvList.length ? 'Ninguno' : 'Todos'}
          </button>
        </div>
        <div class="archive-list">
          {#each archiveCsvList as fname}
            <label class="archive-item">
              <input type="checkbox"
                checked={selectedArchiveCsvs.includes(fname)}
                on:change={() => toggleArchiveCsv(fname)} />
              {fname.split('/').pop()}
            </label>
          {/each}
        </div>
        <button on:click={extractSelected}
          disabled={!selectedArchiveCsvs.length || loadingExtract}
          class="extract-btn"
          class:extract-btn-active={!!selectedArchiveCsvs.length}
        >
          {loadingExtract ? 'Cargando...' : `Cargar ${selectedArchiveCsvs.length} archivo(s)`}
        </button>
      </div>
    {/if}
  </div>

  <!-- Messages -->
  {#if error}
    <div class="msg msg-error">{error}</div>
  {/if}
  {#if successMsg}
    <div class="msg msg-success">{successMsg}</div>
  {/if}

  <!-- Dataset list -->
  <div class="ds-list">
    <p class="section-label">Datasets cargados ({datasets.length})</p>

    {#if datasets.length === 0}
      <p class="ds-empty">
        Ningun dataset cargado.<br />Sube un CSV o ZIP para comenzar.
      </p>
    {:else}
      {#each datasets as ds}
        <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
        <div
          class="ds-card"
          class:ds-card-selected={ds.id === selectedId}
          on:click={() => dispatch('select', { id: ds.id })}
        >
          <div class="ds-card-header">
            <span class="ds-name">{ds.name}</span>
            <button
              class="ds-remove"
              on:click|stopPropagation={() => removeDataset(ds.id)}
              aria-label="Eliminar dataset"
            >
              x
            </button>
          </div>
          <div class="ds-stats">
            <span>{ds.total_rows.toLocaleString()} filas</span>
            <span class="dot">·</span>
            <span>{ds.total_features} cols</span>
            <span class="dot">·</span>
            <span class:warn={ds.missing_total > 0} class:ok={ds.missing_total === 0}>
              {ds.missing_total > 0 ? `${ds.missing_total} nulos` : 'completo'}
            </span>
          </div>
          <div class="ds-footer">
            {fmtBytes(ds.memory_kb)} — ID: {ds.id}
          </div>
        </div>
      {/each}
    {/if}
  </div>
</aside>