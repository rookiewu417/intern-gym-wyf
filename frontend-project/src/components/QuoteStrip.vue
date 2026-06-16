<script setup lang="ts">
import { formatCompact, formatPrice, runtimeLabel } from '../utils/marketFormat'
import type { SnapshotInner } from '../services/marketFeed'
defineProps<{ snapshot?: SnapshotInner; runtimeState?: string }>()
</script>

<template>
  <section class="quote-strip">
    <div><span>Last</span><strong>{{ formatPrice(snapshot?.price) }}</strong></div>
    <div><span>Open</span><strong>{{ formatPrice(snapshot?.open) }}</strong></div>
    <div><span>High</span><strong>{{ formatPrice(snapshot?.high) }}</strong></div>
    <div><span>Low</span><strong>{{ formatPrice(snapshot?.low) }}</strong></div>
    <div><span>Volume</span><strong>{{ formatCompact(snapshot?.volume) }}</strong></div>
    <div><span>State</span><strong>{{ runtimeLabel(runtimeState) }}</strong></div>
  </section>
</template>

<style scoped>
.quote-strip { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 1px; overflow: hidden; border: 1px solid #d7dde5; border-radius: 8px; background: #d7dde5; margin-bottom: 14px; }
.quote-strip div { background: #fff; padding: 12px; min-width: 0; }
.quote-strip span { color: #667085; font-size: 12px; }
.quote-strip strong { display: block; margin-top: 4px; font-size: 18px; }
@media (max-width: 900px) { .quote-strip { grid-template-columns: repeat(2, 1fr); } }
</style>
