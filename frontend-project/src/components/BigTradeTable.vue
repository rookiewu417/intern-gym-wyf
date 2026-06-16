<script setup lang="ts">
import { formatCompact, formatDateTime, formatPrice } from '../utils/marketFormat'
import type { TradeAlert } from '../services/marketFeed'
defineProps<{ alerts: TradeAlert[] }>()
</script>

<template>
  <section class="panel">
    <div class="panel-title"><h2>大额交易</h2><span>{{ alerts.length }}</span></div>
    <table>
      <thead><tr><th>时间</th><th>方向</th><th>价格</th><th>数量</th></tr></thead>
      <tbody>
        <tr v-for="a in alerts" :key="a.id">
          <td>{{ formatDateTime(a.timestamp) }}</td>
          <td>{{ a.side }}</td>
          <td>{{ formatPrice(a.price) }}</td>
          <td>{{ formatCompact(a.volume) }}</td>
        </tr>
        <tr v-if="!alerts.length"><td colspan="4">No current-day alerts</td></tr>
      </tbody>
    </table>
  </section>
</template>

<style scoped>
.panel { border: 1px solid #d7dde5; border-radius: 8px; background: #fff; padding: 14px; min-width: 0; }
.panel-title { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.panel-title span { color: #667085; font-size: 12px; }
h2 { margin: 0; font-size: 15px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { border-bottom: 1px solid #e3e8ef; padding: 8px 6px; text-align: left; }
th { color: #667085; font-weight: 600; }
</style>
