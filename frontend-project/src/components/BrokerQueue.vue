<script setup lang="ts">
import BrokerQueueRow from './BrokerQueueRow.vue'
import type { Gear, QueueLevel } from '../services/marketFeed'

const props = defineProps<{
  ask: QueueLevel[]
  bid: QueueLevel[]
  gear: Gear
  expandedCells: Set<string>
  symbol: string
  fallback?: boolean
  sourceDate?: string
}>()
const emit = defineEmits<{ (e: 'setGear', g: Gear): void; (e: 'toggleCell', key: string): void }>()

const GEARS: Gear[] = [10, 100, 1000]
function key(side: string, position: number) { return `${props.symbol}|${side}|${position}` }
</script>

<template>
  <section class="panel queue-panel">
    <div class="panel-title">
      <h2>Broker Queue</h2>
      <div class="meta">
        <span v-if="fallback" class="fallback">Fallback {{ sourceDate }}</span>
        <div class="gears">
          <button v-for="g in GEARS" :key="g" class="gear" :class="{ active: g === gear }" @click="emit('setGear', g)">{{ g }}</button>
        </div>
      </div>
    </div>
    <div class="queues">
      <div>
        <h3>买盘 Bid</h3>
        <ol>
          <BrokerQueueRow v-for="l in bid" :key="l.id" :level="l" :expanded="expandedCells.has(key('bid', l.position))" @toggle="emit('toggleCell', key('bid', l.position))" />
          <li v-if="!bid.length" class="empty">No bid levels</li>
        </ol>
      </div>
      <div>
        <h3>卖盘 Ask</h3>
        <ol>
          <BrokerQueueRow v-for="l in ask" :key="l.id" :level="l" :expanded="expandedCells.has(key('ask', l.position))" @toggle="emit('toggleCell', key('ask', l.position))" />
          <li v-if="!ask.length" class="empty">No ask levels</li>
        </ol>
      </div>
    </div>
  </section>
</template>

<style scoped>
.panel { border: 1px solid #d7dde5; border-radius: 8px; background: #fff; padding: 14px; }
.panel-title { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.meta { display: flex; align-items: center; gap: 10px; }
.fallback { color: #b54708; font-size: 12px; }
.gears { display: inline-flex; border: 1px solid #cfd7e2; border-radius: 6px; overflow: hidden; }
.gear { padding: 4px 10px; border: 0; background: #fff; font-size: 12px; cursor: pointer; }
.gear.active { background: #0f62fe; color: #fff; }
h2 { margin: 0; font-size: 15px; }
h3 { margin: 0 0 8px; font-size: 13px; }
ol { list-style: none; margin: 0; padding: 0; }
.empty { color: #667085; font-size: 12px; padding: 8px 0; }
/* 买卖各占固定一列，列宽不随档内展开变化 */
.queues { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
@media (max-width: 900px) {
  .queues { grid-template-columns: 1fr; }
  .queues > div { max-height: 360px; overflow-y: auto; }  /* 保证买卖各 >=10 档可滚动 */
}
</style>
