<script setup lang="ts">
import { formatCompact } from '../utils/marketFormat'
import type { BrokerCell as BrokerCellType } from '../services/marketFeed'
defineProps<{ broker: BrokerCellType }>()
</script>

<template>
  <span class="cell"><b>{{ broker.displayName }}</b><em>{{ formatCompact(broker.volume) }}</em></span>
</template>

<style scoped>
.cell { display: inline-flex; gap: 4px; align-items: baseline; padding: 2px 6px; margin: 2px; border: 1px solid #e3e8ef; border-radius: 4px; font-size: 12px; }
.cell em { color: #667085; font-style: normal; }
@media (max-width: 900px) {
  .cell { font-size: 14px; padding: 5px 9px; margin: 3px; }
}
</style>
