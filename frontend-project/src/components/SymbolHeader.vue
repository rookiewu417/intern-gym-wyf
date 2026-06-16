<script setup lang="ts">
import { formatDateTime } from '../utils/marketFormat'
defineProps<{ name: string; symbol: string; dataTime: string }>()
</script>

<template>
  <header class="topbar">
    <div>
      <h1>{{ name || symbol }}</h1>
      <span>{{ symbol }} · 数据时间 {{ formatDateTime(dataTime) }}</span>
    </div>
    <slot name="chip" />
  </header>
</template>

<style scoped>
.topbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
h1 { margin: 0; font-size: 22px; }
.topbar span { color: #667085; font-size: 12px; }
</style>
