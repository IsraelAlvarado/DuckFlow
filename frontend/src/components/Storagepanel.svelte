<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import './styles/Storagepanel.css';

  export let apiBase = 'http://127.0.0.1:8000';
  export let datasets: any[] = [];

  const dispatch = createEventDispatcher();

  interface StorageStatus {
    backend: string;
    configured: boolean;
    folder_id?: string;
    bucket?: string;
    prefix?: string;
    endpoint?: string;
    local_datasets: number;
    available_formats?: string[];
  }

  interface RemoteDataset {
    id: string;
    name: string;
    size_kb?: number;
    modified?: string;
    drive_id?: string;
  }

  const ALL_FORMATS = [
    { id: 'parquet', label: 'Parquet',        desc: 'Formato binario optimizado para analisis' },
    { id: 'csv',     label: 'CSV',            desc: 'Datos tabulares, compatible con Excel' },
    { id: 'py',      label: 'Analisis .py',   desc: 'Script Python con resultados reales + codigo' },
    { id: 'ipynb',   label: 'Analisis .ipynb',desc: 'Jupyter Notebook con resultados + codigo reproducible' },
  ];

  const ALL_SECTIONS = [
    { id: 'overview',      label: 'Resumen general'          },
    { id: 'missing',       label: 'Valores faltantes'        },
    { id: 'numeric',       label: 'Estadisticas numericas'   },
    { id: 'categorical',   label: 'Estadisticas categoricas' },
    { id: 'correlation',   label: 'Correlacion'              },
    { id: 'distributions', label: 'Distribuciones'           },
    { id: 'outliers',      label: 'Outliers (IQR)'           },
    { id: 'normality',     label: 'Normalidad'               },
  ];

  let status: StorageStatus | null = null;
  let statusLoading = false;
  let remoteList: RemoteDataset[] = [];
  let remoteLoading = false;
  let pushLoading = false;
  let pullLoading = false;
  let pullOneLoading = false;
  let log: string[] = [];
  let error = '';

  let pushOneId = '';
  let pushOneLoading = false;
  let selectedFormats: string[] = ['parquet'];
  let selectedSections: string[] = ALL_SECTIONS.map(s => s.id);
  let showFormatPicker = false;
  let pushResult: { pushed: any[]; errors: any[] } | null = null;

  $: pushOneId = datasets[0]?.id ?? '';
  $: selectedMeta = datasets.find((d: any) => d.id === pushOneId) ?? null;
  $: needsSections = selectedFormats.includes('py') || selectedFormats.includes('ipynb');

  onMount(fetchStatus);

  async function fetchStatus(): Promise<void> {
    statusLoading = true; error = '';
    try {
      const res = await fetch(`${apiBase}/api/v1/storage/status`);
      status = await res.json();
    } catch (e) { error = String(e); }
    finally { statusLoading = false; }
  }

  async function fetchRemote(): Promise<void> {
    remoteLoading = true; error = '';
    try {
      const res = await fetch(`${apiBase}/api/v1/storage/list-remote`);
      if (!res.ok) { const d = await res.json(); throw new Error(d.detail); }
      const data = await res.json();
      remoteList = data.remote_datasets ?? [];
    } catch (e) { error = String(e); }
    finally { remoteLoading = false; }
  }

  async function pushAll(): Promise<void> {
    pushLoading = true; error = ''; log = [];
    try {
      const res = await fetch(`${apiBase}/api/v1/storage/push`, { method: 'POST' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail);
      log = [
        `${data.pushed?.length ?? 0} dataset(s) subidos`,
        ...(data.errors?.map((e: any) => `${e.id}: ${e.error}`) ?? []),
      ];
      fetchStatus();
    } catch (e) { error = String(e); }
    finally { pushLoading = false; }
  }

  async function pullAll(): Promise<void> {
    pullLoading = true; error = ''; log = [];
    try {
      const res = await fetch(`${apiBase}/api/v1/storage/pull`, { method: 'POST' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail);
      log = [
        `${data.pulled?.length ?? 0} dataset(s) descargados`,
        ...(data.errors?.map((e: any) => `${e.id}: ${e.error}`) ?? []),
      ];
      dispatch('refresh');
      fetchStatus();
    } catch (e) { error = String(e); }
    finally { pullLoading = false; }
  }

  async function pushOne(): Promise<void> {
    if (!pushOneId || selectedFormats.length === 0) return;
    pushOneLoading = true; error = ''; log = []; pushResult = null;
    try {
      const body: any = { formats: selectedFormats };
      if (needsSections) body.sections = selectedSections;

      const res = await fetch(`${apiBase}/api/v1/storage/push/${pushOneId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail);
      pushResult = data;
      log = [
        ...((data.pushed ?? []).map((p: any) => `${p.filename} subido`)),
        ...((data.errors ?? []).map((e: any) => `${e.format}: ${e.error}`)),
      ];
    } catch (e) { error = String(e); }
    finally { pushOneLoading = false; }
  }

  async function pullOne(id: string): Promise<void> {
    pullOneLoading = true; error = ''; log = [];
    try {
      const res = await fetch(`${apiBase}/api/v1/storage/pull/${id}`, { method: 'POST' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail);
      log = [`Dataset "${id}" descargado y registrado localmente`];
      dispatch('refresh');
    } catch (e) { error = String(e); }
    finally { pullOneLoading = false; }
  }

  function toggleFormat(id: string): void {
    selectedFormats = selectedFormats.includes(id)
      ? selectedFormats.filter(f => f !== id)
      : [...selectedFormats, id];
  }

  function toggleSection(id: string): void {
    selectedSections = selectedSections.includes(id)
      ? selectedSections.filter(s => s !== id)
      : [...selectedSections, id];
  }

  function toggleAllSections(): void {
    selectedSections = selectedSections.length === ALL_SECTIONS.length
      ? []
      : ALL_SECTIONS.map(s => s.id);
  }

  function backendLabel(b: string): string {
    if (b === 'gdrive') return 'Google Drive';
    if (b === 's3') return 'S3 / MinIO / R2';
    return 'Sin backend';
  }

  function fmtLabel(id: string): string {
    return ALL_FORMATS.find(f => f.id === id)?.label ?? id;
  }
</script>

<div class="storage-panel">
  <h3 class="panel-title">Almacenamiento y sincronizacion</h3>
  <p class="panel-desc">
    Datasets persistidos localmente en DuckDB + Parquet. Sincroniza con Google Drive o S3
    eligiendo exactamente que archivos subir por cada dataset.
  </p>

  <section class="card">
    <div class="card-header">
      <span class="card-title">Almacenamiento local (DuckDB + Parquet)</span>
      <span class="badge badge-ok">Activo</span>
    </div>
    <p class="card-desc">
      Cada dataset se guarda como <code>.parquet</code> en <code>data/datasets/</code>
      y su metadata en <code>data/catalog.duckdb</code>. Los datasets sobreviven reinicios.
    </p>
    <div class="kpi-row">
      <div class="kpi"><div class="kpi-val">{status?.local_datasets ?? '—'}</div><div class="kpi-label">Datasets locales</div></div>
      <div class="kpi"><div class="kpi-val">DuckDB</div><div class="kpi-label">Catalogo</div></div>
      <div class="kpi"><div class="kpi-val">Parquet</div><div class="kpi-label">Formato base</div></div>
    </div>
  </section>

  <section class="card">
    <div class="card-header">
      <span class="card-title">Backend de nube</span>
      {#if statusLoading}
        <span class="badge badge-neutral">Verificando...</span>
      {:else if status?.configured}
        <span class="badge badge-ok">{backendLabel(status.backend)}</span>
      {:else}
        <span class="badge badge-warn">No configurado</span>
      {/if}
    </div>

    {#if status?.configured}
      <div class="detail-grid">
        {#if status.folder_id}
          <span class="detail-label">Folder ID</span><code class="detail-val">{status.folder_id}</code>
        {/if}
        {#if status.bucket}
          <span class="detail-label">Bucket</span><code class="detail-val">{status.bucket}</code>
        {/if}
        {#if status.prefix}
          <span class="detail-label">Prefijo</span><code class="detail-val">{status.prefix}</code>
        {/if}
        {#if status.endpoint}
          <span class="detail-label">Endpoint</span><code class="detail-val">{status.endpoint}</code>
        {/if}
      </div>

      <div class="actions-row">
        <button class="btn btn-primary" on:click={pushAll} disabled={pushLoading}>
          {pushLoading ? 'Subiendo...' : 'Subir todos (Parquet)'}
        </button>
        <button class="btn btn-secondary" on:click={pullAll} disabled={pullLoading}>
          {pullLoading ? 'Descargando...' : 'Descargar todos'}
        </button>
        <button class="btn btn-ghost" on:click={fetchRemote} disabled={remoteLoading}>
          {remoteLoading ? '...' : 'Ver remotos'}
        </button>
      </div>

      {#if datasets.length > 0}
        <div class="push-one-block">
          <div class="push-one-header">
            <span class="push-one-title">Subir dataset con formato elegido</span>
            <button
              class="toggle-picker-btn"
              on:click={() => (showFormatPicker = !showFormatPicker)}
            >
              {showFormatPicker ? 'Ocultar opciones' : 'Configurar'}
            </button>
          </div>

          <div class="push-one-row">
            <select class="select flex-1" bind:value={pushOneId}>
              {#each datasets as ds}
                <option value={ds.id}>{ds.name}</option>
              {/each}
            </select>
            <div class="format-chips">
              {#each selectedFormats as f}
                <span class="chip chip-active">{fmtLabel(f)}</span>
              {/each}
              {#if selectedFormats.length === 0}
                <span class="chip chip-warn">Elige al menos un formato</span>
              {/if}
            </div>
            <button
              class="btn btn-sm btn-primary"
              on:click={pushOne}
              disabled={pushOneLoading || !pushOneId || selectedFormats.length === 0}
            >
              {pushOneLoading ? '...' : 'Subir'}
            </button>
          </div>

          {#if showFormatPicker}
            <div class="picker-panel">
              <p class="picker-label">Formatos a subir</p>
              <div class="format-grid">
                {#each ALL_FORMATS as fmt}
                  <label
                    class="format-card"
                    class:format-card-active={selectedFormats.includes(fmt.id)}
                  >
                    <input
                      type="checkbox"
                      checked={selectedFormats.includes(fmt.id)}
                      on:change={() => toggleFormat(fmt.id)}
                    />
                    <div class="format-card-body">
                      <span class="format-card-badge">{fmt.id.toUpperCase()}</span>
                      <span class="format-card-label">{fmt.label}</span>
                      <span class="format-card-desc">{fmt.desc}</span>
                    </div>
                  </label>
                {/each}
              </div>

              {#if needsSections}
                <div class="sections-block">
                  <div class="sections-header">
                    <p class="picker-label" style="margin:0;">Secciones del analisis</p>
                    <button class="tiny-btn" on:click={toggleAllSections}>
                      {selectedSections.length === ALL_SECTIONS.length ? 'Ninguna' : 'Todas'}
                    </button>
                  </div>
                  <div class="sections-grid">
                    {#each ALL_SECTIONS as sec, i}
                      <label
                        class="section-check"
                        class:section-check-active={selectedSections.includes(sec.id)}
                      >
                        <input
                          type="checkbox"
                          checked={selectedSections.includes(sec.id)}
                          on:change={() => toggleSection(sec.id)}
                        />
                        <span class="section-num">{String(i + 1).padStart(2, '0')}</span>
                        {sec.label}
                      </label>
                    {/each}
                  </div>
                  {#if selectedSections.length === 0}
                    <p class="warn-text">Selecciona al menos una seccion.</p>
                  {/if}
                </div>
              {/if}

              {#if selectedMeta}
                <div class="ds-info-row">
                  <span class="ds-info-badge">
                    {selectedMeta.name} &nbsp;·&nbsp;
                    {selectedMeta.total_rows?.toLocaleString()} filas &nbsp;·&nbsp;
                    {selectedMeta.total_features} cols
                  </span>
                </div>
              {/if}
            </div>
          {/if}

          {#if pushResult}
            <div class="push-result">
              {#if pushResult.pushed?.length}
                <p class="result-ok-title">Subidos correctamente:</p>
                {#each pushResult.pushed as p}
                  <p class="result-ok-line">{p.filename}</p>
                {/each}
              {/if}
              {#if pushResult.errors?.length}
                <p class="result-err-title">Errores:</p>
                {#each pushResult.errors as e}
                  <p class="result-err-line">{e.format}: {e.error}</p>
                {/each}
              {/if}
            </div>
          {/if}
        </div>
      {/if}

      {#if remoteList.length > 0}
        <div class="remote-list">
          <p class="list-header">{remoteList.length} archivo(s) en la nube</p>
          {#each remoteList as r}
            <div class="remote-item">
              <div class="remote-info">
                <span class="remote-name">{r.name}</span>
                {#if r.size_kb}<span class="remote-meta">{r.size_kb} KB</span>{/if}
                {#if r.modified}<span class="remote-meta">{r.modified.slice(0, 10)}</span>{/if}
              </div>
              <button
                class="btn btn-sm btn-ghost"
                on:click={() => pullOne(r.id)}
                disabled={pullOneLoading}
              >Jalar</button>
            </div>
          {/each}
        </div>
      {/if}

    {:else}
      <div class="setup-box">
        <p class="setup-title">Configurar backend en <code>.env</code></p>
        <div class="env-block">
          <p class="env-comment"># Opcion A — Google Drive</p>
          <p class="env-line">STORAGE_BACKEND=gdrive</p>
          <p class="env-line">GDRIVE_FOLDER_ID=1AbCdEfGhIjK...</p>
          <p class="env-line">GOOGLE_APPLICATION_CREDENTIALS=credentials.json</p>
          <br/>
          <p class="env-comment"># Opcion B — S3 / MinIO / Cloudflare R2</p>
          <p class="env-line">STORAGE_BACKEND=s3</p>
          <p class="env-line">S3_BUCKET=mi-bucket</p>
          <p class="env-line">AWS_ACCESS_KEY_ID=AKI...</p>
          <p class="env-line">AWS_SECRET_ACCESS_KEY=...</p>
          <p class="env-line">S3_ENDPOINT=https://... # solo para MinIO/R2</p>
        </div>
        <div class="deps-box">
          <p class="deps-title">Dependencias:</p>
          <code>pip install google-auth google-api-python-client pyarrow</code>
          <code>pip install boto3 pyarrow</code>
        </div>
      </div>
    {/if}
  </section>

  {#if error}
    <div class="alert alert-error">{error}</div>
  {/if}
  {#if log.length}
    <div class="log-box">
      {#each log as line}
        <p class="log-line" class:log-error={line.startsWith('✗')}>{line}</p>
      {/each}
    </div>
  {/if}

  <button class="btn btn-ghost btn-sm" on:click={fetchStatus} style="margin-top: 8px;">
    Actualizar estado
  </button>
</div>