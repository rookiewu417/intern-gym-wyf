<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  type IChartApi,
  type ISeriesApi,
} from 'lightweight-charts'
import { toCandles, toVolumes } from '../utils/chartData'
import { formatDateTime } from '../utils/marketFormat'
import type { MarketBar } from '../services/marketFeed'

const props = defineProps<{
  bars: MarketBar[]
  symbol: string
  name: string
  dataTime: string
}>()

const host = ref<HTMLDivElement | null>(null)
let chart: IChartApi | null = null
let candleSeries: ISeriesApi<'Candlestick'> | null = null
let volumeSeries: ISeriesApi<'Histogram'> | null = null

function build() {
  if (!host.value) return
  chart = createChart(host.value, {
    autoSize: true,
    layout: { background: { color: '#fff' }, textColor: '#344054' },
  })
  // K 线在默认 pane 0
  candleSeries = chart.addSeries(CandlestickSeries, {
    upColor: '#0f62fe',
    downColor: '#da1e28',
    borderVisible: false,
    wickUpColor: '#0f62fe',
    wickDownColor: '#da1e28',
  })
  // 成交量放第二个 pane（paneIndex=1），与 K 线结构分离、绝不重叠
  volumeSeries = chart.addSeries(HistogramSeries, { priceFormat: { type: 'volume' } }, 1)
  render()
}

function render() {
  if (!candleSeries || !volumeSeries) return
  candleSeries.setData(toCandles(props.bars))
  volumeSeries.setData(toVolumes(props.bars))
  chart?.timeScale().fitContent()
}

function dispose() {
  chart?.remove()
  chart = null; candleSeries = null; volumeSeries = null
}

function ensureChart() {
  if (!chart && props.bars.length) build()
}

onMounted(ensureChart)
onBeforeUnmount(dispose)
// 切 symbol：销毁并（若有 bars）重建，防 series/canvas 泄漏
watch(() => props.symbol, () => { dispose(); ensureChart() })
// bars 到达：首次构建图表，之后仅更新数据
watch(() => props.bars, () => { if (!chart) ensureChart(); else render() }, { deep: false })
</script>

<template>
  <section class="panel chart-panel">
    <div class="panel-title">
      <h2>{{ name || symbol }} · 分钟</h2>
      <span>{{ formatDateTime(dataTime) }}</span>
    </div>
    <!-- v-show 保留 DOM（ref 可用），display:none 时 createChart 仍可挂载 -->
    <div v-show="bars.length" ref="host" class="chart-host"></div>
    <div v-if="!bars.length" class="empty">Awaiting data…</div>
  </section>
</template>

<style scoped>
.panel {
  border: 1px solid #d7dde5;
  border-radius: 8px;
  background: #fff;
  padding: 14px;
  min-width: 0;
}
.panel-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.panel-title span {
  color: #667085;
  font-size: 12px;
}
h2 {
  margin: 0;
  font-size: 15px;
}
.chart-host {
  height: 340px;
}
.empty {
  height: 340px;
  display: grid;
  place-items: center;
  color: #667085;
}
@media (max-width: 900px) {
  .chart-host,
  .empty {
    height: 280px;
  }
}
</style>
