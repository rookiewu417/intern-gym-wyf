<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useMarketStore } from './stores/marketStore'
import { MarketFeedClient } from './services/marketFeed'
import type { Gear } from './services/marketFeed'
import Watchlist from './components/Watchlist.vue'
import ConnectionChip from './components/ConnectionChip.vue'
import SymbolHeader from './components/SymbolHeader.vue'
import QuoteStrip from './components/QuoteStrip.vue'
import ChartPanel from './components/ChartPanel.vue'
import BigTradeTable from './components/BigTradeTable.vue'
import BrokerQueue from './components/BrokerQueue.vue'

const SYMBOLS = ['02723.HK', '02675.HK', '00100.HK', '02513.HK', '06082.HK']
const WS_URL = import.meta.env.VITE_WS_URL || 'ws://127.0.0.1:9021/ws'

const store = useMarketStore()
if (!store.activeSymbol) store.setActiveSymbol(SYMBOLS[0])

// 移动端分段标签：一次只显示一个面板，让每块都能用大字号铺满屏幕
const mobileTab = ref<'chart' | 'trades' | 'queue'>('chart')

const names = computed<Record<string, string>>(() => {
  const out: Record<string, string> = {}
  for (const s of SYMBOLS) out[s] = store.records[s]?.snapshot.name || ''
  return out
})
const active = computed(() => store.activeRecord)
const ask = computed(() => store.visibleLevels('ask'))
const bid = computed(() => store.visibleLevels('bid'))

let client: MarketFeedClient | null = null

onMounted(() => {
  client = new MarketFeedClient(WS_URL, {
    onStatus: (s) => store.setConnectionStatus(s),
    onSnapshot: (symbol, payload, seq) => store.setSnapshot(symbol, payload, seq),
    onDelta: (symbol, payload, seq) => store.applyDelta(symbol, payload, seq),
  })
  client.connect()
  client.requestSnapshots(SYMBOLS)
})
onBeforeUnmount(() => client?.close())

function onAdd(symbol: string) {
  store.setActiveSymbol(symbol)
  client?.requestSnapshots([symbol])
}
function setGear(g: Gear) { store.setGear(g) }
function toggleCell(key: string) { store.toggleCell(key) }

const TABS: { key: 'chart' | 'trades' | 'queue'; label: string }[] = [
  { key: 'chart', label: '图表' },
  { key: 'trades', label: '大额交易' },
  { key: 'queue', label: '盘口' },
]
</script>

<template>
  <main class="terminal">
    <Watchlist :symbols="SYMBOLS" :active-symbol="store.activeSymbol" :names="names"
      @select="store.setActiveSymbol" @add="onAdd" />
    <section class="workspace">
      <SymbolHeader :name="active?.snapshot.name || ''" :symbol="store.activeSymbol" :data-time="store.activeDataTime">
        <template #chip><ConnectionChip :status="store.displayStatus" /></template>
      </SymbolHeader>
      <QuoteStrip :snapshot="active?.snapshot" :runtime-state="active?.freshness.runtime_state" />

      <nav class="mtabs" role="tablist">
        <button v-for="t in TABS" :key="t.key" type="button" role="tab"
          :aria-selected="mobileTab === t.key" :class="{ active: mobileTab === t.key }"
          @click="mobileTab = t.key">{{ t.label }}</button>
      </nav>

      <section class="market-grid">
        <ChartPanel class="slot" :class="{ 'm-active': mobileTab === 'chart' }"
          :bars="active?.minuteBars || []" :symbol="store.activeSymbol"
          :name="active?.snapshot.name || ''" :data-time="store.activeDataTime" />
        <BigTradeTable class="slot" :class="{ 'm-active': mobileTab === 'trades' }" :alerts="store.currentAlerts" />
        <BrokerQueue class="full slot" :class="{ 'm-active': mobileTab === 'queue' }"
          :ask="ask" :bid="bid" :gear="store.brokerQueueGear"
          :expanded-cells="store.expandedCells" :symbol="store.activeSymbol"
          :fallback="active?.brokerQueue.fallback" :source-date="active?.brokerQueue.sourceDate"
          @set-gear="setGear" @toggle-cell="toggleCell" />
      </section>
    </section>
  </main>
</template>

<style scoped>
.terminal { display: grid; grid-template-columns: 224px minmax(0, 1fr); min-height: 100vh; font-family: Inter, system-ui, sans-serif; color: #18212f; background: #f7f9fc; }
.workspace { min-width: 0; padding: 16px; }
.market-grid { display: grid; grid-template-columns: minmax(0, 1.3fr) minmax(300px, 0.7fr); gap: 14px; }
.market-grid > .full { grid-column: 1 / -1; }
.mtabs { display: none; }

@media (max-width: 900px) {
  .terminal { grid-template-columns: 1fr; }
  .workspace { padding: 12px 14px 28px; font-size: 16px; }
  .market-grid { grid-template-columns: 1fr; gap: 0; }

  /* 分段标签：sticky 顶部，随时切面板 */
  .mtabs { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; margin: 2px 0 14px; position: sticky; top: 0; z-index: 4; background: #f7f9fc; padding: 6px 0; }
  .mtabs button { height: 46px; border: 1px solid #cfd7e2; border-radius: 10px; background: #fff; font-size: 16px; font-weight: 600; color: #344054; cursor: pointer; }
  .mtabs button.active { background: #0f62fe; border-color: #0f62fe; color: #fff; }

  /* 移动端一次只显示激活面板 */
  .slot { display: none; }
  .slot.m-active { display: block; }
}
</style>
