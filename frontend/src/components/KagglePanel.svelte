<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import './styles/KagglePanel.css';

  export let datasets: any[] = [];
  export let apiBase = 'http://127.0.0.1:8000';
  export let selectedDatasetId: string | null = null;

  const dispatch = createEventDispatcher();

  let searchQuery = '';
  let searchResults: any[] = [];
  let searchLoading = false;
  let searchError = '';

  let downloadRef = '';
  let downloadLoading = false;
  let downloadError = '';
  let downloadSuccess = '';

  let uploadTitle = '';
  let uploadSlug = '';
  let uploadUsername = '';
  let uploadPublic = false;
  let uploadNewVersion = false;
  let uploadLoading = false;
  let uploadError = '';
  let uploadResult: { url: string; message: string } | null = null;

  $: selectedMeta = datasets.find(d => d.id === selectedDatasetId) ?? null;
  $: if (uploadTitle && !uploadSlug) {
    uploadSlug = uploadTitle.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  }

  async function searchKaggle(): Promise<void> {
    searchLoading = true;
    searchError = '';
    searchResults = [];
    try {
      const res = await fetch(`${apiBase}/api/v1/kaggle/search?q=${encodeURIComponent(searchQuery)}`);
      if (!res.ok) { const d = await res.json(); throw new Error(d.detail); }
      const data = await res.json();
      searchResults = data.datasets ?? [];
    } catch (e) {
      searchError = String(e);
    } finally {
      searchLoading = false;
    }
  }

  function useDatasetRef(ref: string): void {
    downloadRef = ref;
  }

  async function downloadDataset(): Promise<void> {
    if (!downloadRef.trim()) return;
    downloadLoading = true;
    downloadError = '';
    downloadSuccess = '';
    try {
      const res = await fetch(`${apiBase}/api/v1/kaggle/download`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dataset: downloadRef.trim() }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail);
      const count = data.loaded?.length ?? 0;
      downloadSuccess = `${count} archivo(s) cargado(s) desde "${downloadRef}".`;
      if (data.errors?.length) downloadSuccess += ` (${data.errors.length} errores)`;
      dispatch('refresh');
    } catch (e) {
      downloadError = String(e);
    } finally {
      downloadLoading = false;
    }
  }

  async function uploadDataset(): Promise<void> {
    if (!selectedDatasetId || !uploadTitle || !uploadUsername) return;
    uploadLoading = true;
    uploadError = '';
    uploadResult = null;
    try {
      const res = await fetch(`${apiBase}/api/v1/kaggle/upload`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          dataset_id: selectedDatasetId,
          title: uploadTitle,
          slug: uploadSlug,
          username: uploadUsername,
          is_public: uploadPublic,
          new_version: uploadNewVersion,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail);
      uploadResult = { url: data.url, message: data.message };
    } catch (e) {
      uploadError = String(e);
    } finally {
      uploadLoading = false;
    }
  }

  function handleSearchKey(e: KeyboardEvent): void {
    if (e.key === 'Enter') searchKaggle();
  }
</script>

<div class="kaggle-panel">
  <section class="card">
    <h4 class="section-title">Buscar en Kaggle</h4>
    <p class="section-desc">Encuentra datasets publicos de Kaggle para importar directamente.</p>

    <div class="search-row">
      <input
        class="text-input flex-1"
        bind:value={searchQuery}
        on:keydown={handleSearchKey}
        placeholder="Ej: supply chain, sales forecasting..."
      />
      <button class="btn btn-primary" on:click={searchKaggle} disabled={searchLoading}>
        {searchLoading ? 'Buscando...' : 'Buscar'}
      </button>
    </div>

    {#if searchError}
      <div class="alert alert-error">{searchError}</div>
    {/if}

    {#if searchResults.length > 0}
      <div class="results-list">
        {#each searchResults as ds}
          <div class="result-item">
            <div class="result-info">
              <span class="result-ref">{ds.ref ?? ds.title ?? '—'}</span>
              <span class="result-meta">
                {#if ds.size} {ds.size} &nbsp;·&nbsp; {/if}
                {#if ds.lastUpdated} Actualizado: {ds.lastUpdated} {/if}
              </span>
            </div>
            <button
              class="btn btn-sm btn-ghost"
              on:click={() => useDatasetRef(ds.ref ?? '')}
              title="Usar este dataset"
            >
              Usar
            </button>
          </div>
        {/each}
      </div>
    {:else if !searchLoading && searchQuery}
      <p class="muted-text">Sin resultados. Intenta con otro termino.</p>
    {/if}
  </section>

  <section class="card">
    <h4 class="section-title">Descargar Dataset</h4>
    <p class="section-desc">
      Descarga cualquier dataset de Kaggle usando su referencia <code>propietario/slug</code>.
    </p>

    <div class="search-row">
      <input
        class="text-input flex-1"
        bind:value={downloadRef}
        placeholder="Ej: rtatman/chocolate-bar-ratings"
      />
      <button class="btn btn-primary" on:click={downloadDataset} disabled={downloadLoading || !downloadRef.trim()}>
        {downloadLoading ? 'Descargando...' : 'Descargar'}
      </button>
    </div>

    {#if downloadLoading}
      <div class="progress-bar">
        <div class="progress-bar-fill"></div>
      </div>
      <p class="muted-text" style="margin-top: 6px;">Descargando y descomprimiendo... puede tomar varios segundos.</p>
    {/if}

    {#if downloadError}
      <div class="alert alert-error">{downloadError}</div>
    {/if}
    {#if downloadSuccess}
      <div class="alert alert-success">{downloadSuccess}</div>
    {/if}

    <div class="info-box">
      <strong>Autenticacion:</strong> Configura <code>KAGGLE_USERNAME</code> y
      <code>api_token_kaggle</code> en tu archivo <code>.env</code>.
      Los datasets privados requieren permisos activos en tu cuenta.
    </div>
  </section>

  <section class="card">
    <h4 class="section-title">Publicar en Kaggle</h4>
    <p class="section-desc">
      Sube el dataset activo como dataset en tu cuenta de Kaggle.
    </p>

    {#if !selectedDatasetId}
      <div class="empty-state">Selecciona un dataset activo para publicarlo.</div>
    {:else}
      <div class="selected-badge">
        Dataset seleccionado: <strong>{selectedMeta?.name}</strong>
        &nbsp;·&nbsp; {selectedMeta?.total_rows?.toLocaleString()} filas
      </div>

      <div class="form-grid">
        <div class="form-field">
          <label class="field-label" for="up-username">Usuario de Kaggle</label>
          <input id="up-username" class="text-input" bind:value={uploadUsername} placeholder="tu_usuario_kaggle" />
        </div>
        <div class="form-field">
          <label class="field-label" for="up-title">Titulo del dataset</label>
          <input id="up-title" class="text-input" bind:value={uploadTitle} placeholder="Mi Dataset de Ventas" />
        </div>
        <div class="form-field">
          <label class="field-label" for="up-slug">Slug (ID en URL)</label>
          <input id="up-slug" class="text-input" bind:value={uploadSlug} placeholder="mi-dataset-ventas" />
        </div>
      </div>

      <div class="checkbox-row">
        <label class="checkbox-label">
          <input type="checkbox" bind:checked={uploadPublic} />
          Hacer publico
        </label>
        <label class="checkbox-label">
          <input type="checkbox" bind:checked={uploadNewVersion} />
          Crear nueva version (si ya existe)
        </label>
      </div>

      <button
        class="btn btn-primary"
        on:click={uploadDataset}
        disabled={uploadLoading || !uploadTitle || !uploadUsername}
      >
        {uploadLoading ? 'Subiendo...' : 'Publicar en Kaggle'}
      </button>

      {#if uploadError}
        <div class="alert alert-error">{uploadError}</div>
      {/if}

      {#if uploadResult}
        <div class="alert alert-success">
          Dataset publicado correctamente.
          <a href={uploadResult.url} target="_blank" rel="noopener noreferrer" class="link">
            Ver en Kaggle
          </a>
        </div>
      {/if}
    {/if}
  </section>
</div>