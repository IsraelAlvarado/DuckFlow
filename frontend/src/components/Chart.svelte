<script>
  import { onMount, onDestroy } from 'svelte';
  import * as echarts from 'echarts';

  /** @type {import('echarts').EChartsOption} */
  export let options = { series: [] };

  /** @type {HTMLDivElement | null} */
  let chartContainer = null;

  /** @type {import('echarts').ECharts | null} */
  let chartInstance = null;

  // Reactividad: Actualización si las opciones cambian desde el componente padre
  $: if (chartInstance && options) {
    chartInstance.setOption(options);
  }

  onMount(() => {
    if (chartContainer) {
      chartInstance = echarts.init(chartContainer);
      chartInstance.setOption(options);
    }

    const handleResize = () => {
      if (chartInstance) {
        chartInstance.resize();
      }
    };
    
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
    };
  });

  onDestroy(() => {
    if (chartInstance) {
      chartInstance.dispose();
    }
  });
</script>

<div bind:this={chartContainer} style="width: 100%; height: 100%;"></div>